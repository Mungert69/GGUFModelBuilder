using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using NetworkMonitor.Connection;
using NetworkMonitor.Utils;
using NetworkMonitor.Objects;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using Microsoft.IdentityModel.Tokens;
using NetworkMonitor.Objects.Repository;


namespace NetworkMonitor.Processor.Services
{

    public interface IAuthService
    {
        Task InitializeAsync();
        Task ConnectDeviceAsync();
        Task PollForTokenAsync();
    }
    public class AuthService : IAuthService
    {
        private readonly string _baseFusionAuthURL = "https://auth.freenetworkmonitor.click:2096";
        private readonly string _grantType = "urn:ietf:params:oauth:grant-type:device_code";
        private readonly string _clientId = "e37f9939-3500-4133-ac56-c571a9a969b9";
        private string _tokenEndpoint;
        private string _deviceAuthEndpoint;
        private string _deviceCode;
        private int _intervalSeconds = 5;
        private NetConnectConfig _netConfig;
        private ILogger _logger;

        private IRabbitRepo _rabbitRepo;


        public AuthService(ILogger logger, NetConnectConfig netConfig, IRabbitRepo rabbitRepo)
        {
            _netConfig = netConfig;
            _logger = logger;
            _rabbitRepo = rabbitRepo;
        }

        public async Task InitializeAsync()
        {
            using var httpClient = new HttpClient();
            var discoveryUrl = $"{_baseFusionAuthURL}/.well-known/openid-configuration";
            var discoveryResponse = await httpClient.GetAsync(discoveryUrl);

            if (!discoveryResponse.IsSuccessStatusCode)
            {
                _logger.LogError($"Error: {discoveryResponse.StatusCode}");
                return;
            }

            var discoveryDataString = await discoveryResponse.Content.ReadAsStringAsync();
            try
            {
                var discoveryData = JsonUtils.GetJsonElementFromString(discoveryDataString);
                _deviceAuthEndpoint = discoveryData.GetProperty("device_authorization_endpoint").GetString();
                _tokenEndpoint = discoveryData.GetProperty("token_endpoint").GetString();
            }
            catch (JsonException ex)
            {
                _logger.LogError($"JSON Parsing Error: {ex.Message}");
            }
        }

        public async Task ConnectDeviceAsync()
        {
            using var httpClient = new HttpClient();
            var content = new FormUrlEncodedContent(new[]
            {
                new KeyValuePair<string, string>("client_id", _clientId),
                new KeyValuePair<string, string>("scope", "offline_access")
            });

            var deviceAuthResponse = await httpClient.PostAsync(_deviceAuthEndpoint, content);
            var deviceAuthDataString = await deviceAuthResponse.Content.ReadAsStringAsync();
            var deviceAuthData = JsonUtils.GetJsonElementFromString(deviceAuthDataString);

            _intervalSeconds = deviceAuthData.GetProperty("interval").GetInt32();
            _deviceCode = deviceAuthData.GetProperty("device_code").GetString();

            string userCode = deviceAuthData.GetProperty("user_code").GetString();
            int ucLen = userCode.Length / 2;
            userCode = userCode.Substring(0, ucLen) + "-" + userCode.Substring(ucLen);

            _logger.LogInformation($"User code: {userCode}");
            _logger.LogInformation($"Verification URL: {deviceAuthData.GetProperty("verification_uri").GetString()}");
            _netConfig.ClientAuthUrl = deviceAuthData.GetProperty("verification_uri_complete").GetString();
            _logger.LogInformation($"Complete verification URL: {_netConfig.ClientAuthUrl}");

        }

        public async Task PollForTokenAsync()
        {
            _logger.LogInformation("Starting polling device auth endpoint, please wait...");

            while (true)
            {
                try
                {
                    var pollingContent = new FormUrlEncodedContent(new[]
                        {
                            new KeyValuePair<string, string>("device_code", _deviceCode),
                            new KeyValuePair<string, string>("grant_type", _grantType),
                            new KeyValuePair<string, string>("client_id", _clientId)
                            });
                    var httpClient = new HttpClient();
                    var tokenResponse = await httpClient.PostAsync(_tokenEndpoint, pollingContent);
                    if (tokenResponse.IsSuccessStatusCode)
                    {
                        var oldAppID = _netConfig.AppID;
                        var tokenDataString = await tokenResponse.Content.ReadAsStringAsync();
                        var tokenData = JsonUtils.GetJsonElementFromString(tokenDataString);
                        var accessToken = tokenData.GetProperty("access_token").GetString();
                        var userInfo = await GetUserInfoFromToken(accessToken);
                        var updatedSystemUrl = new SystemUrl
                        {
                            ExternalUrl = $"https://monitorProcessor{userInfo.UserID}.local",
                            IPAddress = _netConfig.LocalSystemUrl.IPAddress,
                            RabbitHostName = _netConfig.LocalSystemUrl.RabbitHostName,
                            RabbitPort = _netConfig.LocalSystemUrl.RabbitPort,
                            RabbitInstanceName = $"monitorProcessor{userInfo.UserID}",
                            RabbitUserName = userInfo.UserID,
                            RabbitPassword = accessToken,
                            RabbitVHost = _netConfig.LocalSystemUrl.RabbitVHost
                        };

                        var processorObj = new ProcessorObj();

                        processorObj.Location = userInfo.Email + " - Local";
                        processorObj.AppID = userInfo.UserID;
                        processorObj.Owner = userInfo.UserID;
                        processorObj.IsPrivate = true;
                        if (oldAppID != userInfo.UserID)
                        {
                            processorObj.DateCreated = DateTime.UtcNow;
                            await _rabbitRepo.PublishAsync<Tuple<string, string>>("changeProcessorAppID", new Tuple<string, string>(oldAppID, processorObj.AppID));
                        }

                        _netConfig.Owner=userInfo.UserID;
                        // Update the AppID and LocalSystemUrl
                        await _netConfig.SetAppIDAsync(processorObj.AppID);
                        await _netConfig.SetLocalSystemUrlAsync(updatedSystemUrl);

                        // Now publish the message
                        await _rabbitRepo.PublishAsync<ProcessorObj>("userUpdateProcessor", processorObj);

                        _logger.LogInformation(" Success : Token successfully received.");
                        break;
                    }
                    else
                    {
                        var errorDataString = await tokenResponse.Content.ReadAsStringAsync();
                        var errorData = JsonUtils.GetJsonElementFromString(errorDataString);
                        _logger.LogError($" Error  : during polling: {errorDataString}");
                    }
                    //_logger.LogInformation("Polling device auth endpoint, please wait...");
                    await Task.Delay(_intervalSeconds * 1000);
                }
                catch (Exception ex)
                {
                    _logger.LogError($" Error : An error occurred during the token request: {ex.Message}");
                }
            }
        }

        private async Task<UserInfo> GetUserInfoFromToken(string accessToken)
        {
            var tokenHandler = new JwtSecurityTokenHandler();

            try
            {
                // Decode the JWT without validating it
                var jwt = tokenHandler.ReadJwtToken(accessToken);


                var userInfo = new UserInfo();

                foreach (var claim in jwt.Claims)
                {
                    switch (claim.Type)
                    {
                        case "sub":
                            userInfo.UserID = claim.Value;
                            userInfo.Sub = claim.Value;
                            break;
                        case "email":
                            userInfo.Email = claim.Value;
                            break;
                        case "verified":
                            userInfo.Email_verified = bool.Parse(claim.Value);
                            break;
                        case "fullName":
                            userInfo.Name = claim.Value;
                            break;
                        case "name":
                            userInfo.Name = claim.Value;
                            break;
                        case "imageUrl":
                            userInfo.Picture = claim.Value;
                            break;

                            // Add more cases for other claim types as needed
                    }
                }


                return userInfo;
            }
            catch (Exception e)
            {
                _logger.LogError($"Error decoding token: {e.Message}");
                return null;
            }
        }
    }
}
