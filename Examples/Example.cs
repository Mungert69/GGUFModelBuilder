using System; // Required base functionality
using System.Text; // For StringBuilder
using System.Collections.Generic; // For collections
using System.Diagnostics; // For debugging (if needed)
using System.Threading.Tasks; // For async/await
using System.Text.RegularExpressions; // For regex operations
using Microsoft.Extensions.Logging; // For logging
using System.Linq; // For LINQ operations
using NetworkMonitor.Objects; // For application-specific objects
using NetworkMonitor.Objects.Repository; // For repository handling
using NetworkMonitor.Objects.ServiceMessage; // For service messaging
using NetworkMonitor.Connection; // For connection handling
using NetworkMonitor.Utils; // For utility methods
using System.Xml.Linq; // For XML handling
using System.IO; // For file operations
using System.Threading; // For CancellationToken
using System.Net; // For FTPWebRequest

namespace NetworkMonitor.Connection
{
    public class FTPConnectionTesterCmdProcessor : CmdProcessor
    {
        public FTPConnectionTesterCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
            : base(logger, cmdProcessorStates, rabbitRepo, netConfig) { }

        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result = new ResultObj();
            try
            {
                // Parse command-line style arguments
                var args = ParseArguments(arguments);
                if (!args.ContainsKey("username") || !args.ContainsKey("password") || !args.ContainsKey("host"))
                {
                    result.Success = false;
                    result.Message = "Invalid arguments. Please provide --username, --password, and --host.";
                    return result;
                }

                string username = args["username"];
                string password = args["password"];
                string host = args["host"];

                _logger.LogInformation($"Testing FTP connection to {host} with username: {username}");

                // Test FTP connection
                var request = (FtpWebRequest)WebRequest.Create($"ftp://{host}");
                request.Credentials = new NetworkCredential(username, password);
                request.Method = WebRequestMethods.Ftp.ListDirectory;

                try
                {
                    using (var response = (FtpWebResponse)await request.GetResponseAsync())
                    {
                        result.Success = true;
                        result.Message = $"FTP connection successful. Response status: {response.StatusDescription}";
                    }
                }
                catch (WebException ex)
                {
                    if (ex.Response is FtpWebResponse ftpResponse)
                    {
                        _logger.LogError($"FTP error: {ftpResponse.StatusDescription}");
                        result.Success = false;
                        result.Message = $"FTP connection failed. Status: {ftpResponse.StatusDescription}";
                    }
                    else
                    {
                        _logger.LogError($"FTP error: {ex.Message}");
                        result.Success = false;
                        result.Message = $"FTP connection failed. Error: {ex.Message}";
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError($"Error testing FTP connection: {ex.Message}");
                result.Success = false;
                result.Message = $"Error testing FTP connection: {ex.Message}";
            }
            return result;
        }
        public override string GetCommandHelp()
        {
            return @"
This command tests an FTP connection by attempting to list the directory contents using provided credentials. 
It validates the FTP server’s response and provides feedback on connectivity.

Usage:
    arguments: A command-line style string containing:
        --username: FTP username.
        --password: FTP password.
        --host: FTP host (e.g., 'ftp.example.com').

Examples:
    - '--username admin --password admin123 --host ftp.example.com':
        Tests FTP connection to 'ftp.example.com' with the specified credentials.
";
        }


        // Helper method to parse command-line style arguments
        private Dictionary<string, string> ParseArguments(string arguments)
        {
            var args = new Dictionary<string, string>();
            var regex = new Regex(@"--(?<key>\w+)\s+(?<value>[^\s]+)");
            var matches = regex.Matches(arguments);

            foreach (Match match in matches)
            {
                args[match.Groups["key"].Value.ToLower()] = match.Groups["value"].Value;
            }

            return args;
        }
    }
}
