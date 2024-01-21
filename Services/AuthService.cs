using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using NetworkMonitor.Connection;
using NetworkMonitor.Utils;
using NetworkMonitor.Utils.Helpers;
using NetworkMonitor.Objects;
using System.Text.Json;
using System.Text;
using Microsoft.Extensions.Logging;
using System.IdentityModel.Tokens.Jwt;
using System.IdentityModel.Tokens;
using System.Security.Claims;
using NetworkMonitor.Objects.Repository;
using System.Threading;


namespace NetworkMonitor.Processor.Services
{

    public interface IAuthService
    {
        Task<ResultObj> InitializeAsync();
        Task<ResultObj> SendAuthRequestAsync();
        Task<ResultObj> PollForTokenAsync();
        Task<ResultObj> PollForTokenAsync(CancellationToken cancellationToken);
    }
    public class AuthService : IAuthService
    {
        private readonly string _grantType = "urn:ietf:params:oauth:grant-type:device_code";
        private string _tokenEndpoint = "";
        private string _deviceAuthEndpoint = "";
        private string _deviceCode = "";
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

        public async Task<ResultObj> InitializeAsync()
        {
            var result = new ResultObj();
            result.Message = " InitializeAsync : ";
            using var httpClient = new HttpClient();
            if (String.IsNullOrEmpty(_netConfig.ClientId))
            {
                result.Message += $" Error: No BaseFusionAuthUrl set . ";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }
            var discoveryUrl = $"{_netConfig.BaseFusionAuthURL}/.well-known/openid-configuration";
            var discoveryResponse = await httpClient.GetAsync(discoveryUrl);

            if (!discoveryResponse.IsSuccessStatusCode)
            {
                result.Message += $"Error: {discoveryResponse.StatusCode}";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }

            var discoveryDataString = await discoveryResponse.Content.ReadAsStringAsync();
            if (string.IsNullOrEmpty(discoveryDataString))
            {
                result.Message += " Error  : Discovery data string is null or empty.";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }

            try
            {
                var discoveryData = JsonUtils.GetJsonElementFromString(discoveryDataString);

                if (discoveryData.TryGetProperty("device_authorization_endpoint", out var deviceAuthEndpointElement))
                {
                    _deviceAuthEndpoint = deviceAuthEndpointElement.GetString()!;
                }
                else
                {
                    result.Message += " Error  : Device authorization endpoint not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }

                if (discoveryData.TryGetProperty("token_endpoint", out var tokenEndpointElement))
                {
                    _tokenEndpoint = tokenEndpointElement.GetString()!;
                }
                else
                {
                    result.Message += " Error  : Token endpoint not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }
            }
            catch (Exception ex)
            {
                result.Message += $" Error : Initialize Auth Connection failed.  Error was : {ex.Message}";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }
            result.Success = true;
            result.Message += " Success : Initilized Auth Connection . ";
            return result;

        }

        public async Task<ResultObj> SendAuthRequestAsync()
        {
            var result = new ResultObj { Message = " SendAuthRequestAsync: " };

            if (String.IsNullOrEmpty(_netConfig.ClientId))
            {
                result.Message += " Error: No ClientId set.";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }

            using var httpClient = new HttpClient();
            var content = new FormUrlEncodedContent(new[]
            {
        new KeyValuePair<string, string>("client_id", _netConfig.ClientId),
        new KeyValuePair<string, string>("scope", "offline_access")
    });

            var deviceAuthResponse = await httpClient.PostAsync(_deviceAuthEndpoint, content);
            var deviceAuthDataString = await deviceAuthResponse.Content.ReadAsStringAsync();

            if (!deviceAuthResponse.IsSuccessStatusCode)
            {
                result.Message += $" Error: {deviceAuthResponse.StatusCode} - Data: {deviceAuthDataString}.";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }

            if (string.IsNullOrEmpty(deviceAuthDataString))
            {
                result.Message += " Error : Device auth data string is null or empty.";
                result.Success = false;
                _logger.LogError(result.Message);
                return result;
            }

            try
            {
                var deviceAuthData = JsonUtils.GetJsonElementFromString(deviceAuthDataString);

                if (deviceAuthData.TryGetProperty("interval", out var intervalElement))
                {
                    _intervalSeconds = intervalElement.GetInt32();
                }
                else
                {
                    result.Message += " Error : Interval not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }

                if (deviceAuthData.TryGetProperty("device_code", out var deviceCodeElement))
                {
                    _deviceCode = deviceCodeElement.GetString()!;
                }
                else
                {
                    result.Message += " Error : Device code not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }

                if (deviceAuthData.TryGetProperty("user_code", out var userCodeElement))
                {
                    string userCode = userCodeElement.GetString()!;
                    int ucLen = userCode.Length / 2;
                    userCode = userCode.Substring(0, ucLen) + "-" + userCode.Substring(ucLen);
                    _logger.LogInformation($" User code: {userCode}");
                }
                else
                {
                    result.Message += " Error : User code not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }

                if (deviceAuthData.TryGetProperty("verification_uri", out var verificationUriElement))
                {
                    _logger.LogInformation($" Verification URL: {verificationUriElement.GetString()}");
                }
                else
                {
                    result.Message += " Error : Verification URI not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }

                if (deviceAuthData.TryGetProperty("verification_uri_complete", out var verificationUriCompleteElement))
                {
                    _netConfig.ClientAuthUrl = verificationUriCompleteElement.GetString()!;
                    _logger.LogInformation($" Complete verification URL: {_netConfig.ClientAuthUrl}");
                }
                else
                {
                    result.Message += " Error : Complete verification URI not found in JSON.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }

                result.Success = true;
                result.Message += " Success : Auth request sent .";
            }
            catch (Exception ex)
            {
                result.Message += $" Error : Could send auth request. Error was : {ex.Message}";
                result.Success = false;
                _logger.LogError(result.Message);
            }

            return result;
        }

        private async Task SetNewRabbitConnection(string rabbitHostName, int rabbitPort)
        {
            bool flag = false;

            if (_netConfig.LocalSystemUrl.RabbitHostName != rabbitHostName)
            {
                _netConfig.LocalSystemUrl.RabbitHostName = rabbitHostName;
                flag = true;
            }
            if (_netConfig.LocalSystemUrl.RabbitPort != rabbitPort)
            {
                _netConfig.LocalSystemUrl.RabbitPort = rabbitPort;
                flag = true;
            }
            if (flag) await _netConfig.SetLocalSystemUrlAsync(_netConfig.LocalSystemUrl);
        }

        public async Task<ResultObj> PollForTokenAsync()
        {
            using var cancellationTokenSource = new CancellationTokenSource();
            return await PollForTokenAsync(cancellationTokenSource.Token);
        }

        public async Task<ResultObj> PollForTokenAsync(CancellationToken cancellationToken)
        {
            var result = new ResultObj { Message = " PollForTokenAsync : " };
            _logger.LogInformation("Starting polling device auth endpoint, please login to authorize and then wait...");
            var stopwatch = new System.Diagnostics.Stopwatch();
            stopwatch.Start();
            while (!cancellationToken.IsCancellationRequested)
            {

                if (stopwatch.Elapsed.TotalSeconds >= 600) // 10 minutes
                {
                    result.Message += "Timeout: Polling exceeded 10 minutes.";
                    result.Success = false;
                    _logger.LogError(result.Message);
                    return result;
                }
                try
                {
                    var pollingContent = new FormUrlEncodedContent(new[]
                    {
                        new KeyValuePair<string, string>("device_code", _deviceCode),
                        new KeyValuePair<string, string>("grant_type", _grantType),
                        new KeyValuePair<string, string>("client_id", _netConfig.ClientId)
                    });

                    var httpClient = new HttpClient();
                    var tokenResponse = await httpClient.PostAsync(_tokenEndpoint, pollingContent);

                    if (tokenResponse.IsSuccessStatusCode)
                    {
                        var oldAppID = _netConfig.AppID;
                        var tokenDataString = await tokenResponse.Content.ReadAsStringAsync();
                        var tokenData = JsonUtils.GetJsonElementFromString(tokenDataString);
                        var accessToken = tokenData.GetProperty("access_token").GetString();

                        if (accessToken == null)
                        {
                            result.Message += " Error : The return data did not contain an access_token string.";
                            _logger.LogError(result.Message);
                            result.Success = false;
                            return result;
                        }

                        var userInfo = GetUserInfoFromToken(accessToken);
                        if (userInfo == null || userInfo.UserID == null)
                        {
                            result.Message += " Error : Could not get user information from the token.";
                            _logger.LogError(result.Message);
                            result.Success = false;
                            return result;
                        }

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
                        /*if (oldAppID != userInfo.UserID)
                        {
                            processorObj.DateCreated = DateTime.UtcNow;
                            await _rabbitRepo.PublishAsync<Tuple<string, string>>("changeProcessorAppID", new Tuple<string, string>(oldAppID, processorObj.AppID));
                        }*/

                        _netConfig.Owner = userInfo.UserID;
                        _netConfig.MonitorLocation = userInfo.Email + " - Local";
                        var loadServerDataString="None";
                        string loadServerUrl = $"https://{_netConfig.LoadServer}/Load/GetLoadServerApi/{userInfo.UserID}";
                        var loadServerResponse = await httpClient.GetAsync(loadServerUrl);
                        if (!loadServerResponse.IsSuccessStatusCode)
                        {
                            result.Message += $" Error : LoadServer API call to {loadServerUrl} failed with status code: {loadServerResponse.StatusCode}.";
                            _logger.LogError(result.Message);
                            result.Success = false;
                            return result;
                        }

                        loadServerDataString = await loadServerResponse.Content.ReadAsStringAsync();
                        if (string.IsNullOrEmpty(loadServerDataString))
                        {
                            result.Message += " Error : LoadServer response data string is null or empty.";
                            _logger.LogError(result.Message);
                            result.Success = false;
                            return result;
                        }

                        RabbitLoadServer loadServer=new RabbitLoadServer();
                        try
                        {
                            var loadResult = JsonUtils.GetObjectFieldFromJson<RabbitLoadServer>(loadServerDataString,"data");
                            var loadResult2 = await APIHelper.GetDataFromResultObjJson<RabbitLoadServer>(loadServerUrl);
                            if (loadResult == null)
                            {
                                result.Message += " Error : Deserialized result from load server was null.";
                                result.Success = false;
                                _logger.LogError(result.Message);
                                return result;
                            }
                          

                            loadServer=loadResult;
                            await SetNewRabbitConnection(loadServer.RabbitHostName+"."+_netConfig.ServiceDomain, loadServer.RabbitPort);
                        }
                        catch (Exception ex)
                        {
                            result.Message += $" Error : Failed to deserialize {loadServerDataString} to SystemUrl. Exception: {ex.Message}";
                            _logger.LogError(result.Message);
                            result.Success = false;
                            return result;
                        }
                        // Update the AppID and LocalSystemUrl
                        await _netConfig.SetAppIDAsync(processorObj.AppID);

                        await _netConfig.SetLocalSystemUrlAsync(updatedSystemUrl);

                        // Now publish the message
                        await _rabbitRepo.PublishAsync<ProcessorObj>("genAuthKey", processorObj);


                        result.Success = true;
                        result.Message += " Success : Token received and processed. ";
                        return result;
                    }
                    else
                    {
                        var errorDataString = await tokenResponse.Content.ReadAsStringAsync();
                        _logger.LogWarning($" Warning : Token not ready yet : {errorDataString}");
                    }

                    await Task.Delay(_intervalSeconds * 1000);
                }
                catch (OperationCanceledException)
                {
                    result.Message += "Polling operation was cancelled.";
                    result.Success = false;
                    _logger.LogInformation(result.Message);
                    return result;
                }
                catch (Exception ex)
                {
                    result.Message += $"An error occurred during the token request: {ex.Message}";
                    _logger.LogError(result.Message);
                    result.Success = false;
                    return result;
                }
            }
            result.Message = " Authorization cancelled .";
            result.Success = false;
            return result;
        }

        private UserInfo? GetUserInfoFromToken(string accessToken)
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
