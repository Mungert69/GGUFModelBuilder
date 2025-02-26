using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using FluentFTP; // Modern FTP library
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Utils;

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

                // Use AsyncFtpClient to test the connection
                using (var ftpClient = new AsyncFtpClient(host, username, password))
                {
                    // Connect to the FTP server asynchronously
                    await ftpClient.Connect(cancellationToken);

                    // Check if the connection was successful
                    if (ftpClient.IsConnected)
                    {
                        result.Success = true;
                        result.Message = "FTP connection successful.";
                    }
                    else
                    {
                        result.Success = false;
                        result.Message = "FTP connection failed: Unable to connect to the server.";
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
This command tests an FTP connection by attempting to connect to the server using provided credentials. 
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
    }
}