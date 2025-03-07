// Make sure to include all these using statements
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
using System.Net; // For HttpClient
using System.Net.Http; // For HttpClient

// Make sure namespace is declared
namespace NetworkMonitor.Connection
{
    // Use cmd procesor type then CmdProcessor for the class name. In this case cmd_processor_type is SimpleHttp and the class SimpleHttpCmdProcessor
    public class SimpleHttpCmdProcessor : CmdProcessor
    {
        // Keep constructor exactly like this
        public SimpleHttpCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
            : base(logger, cmdProcessorStates, rabbitRepo, netConfig) { }

        // Override the RunCommand method
        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result = new ResultObj();

            try
            {
                if (string.IsNullOrWhiteSpace(arguments))
                {
                    result.Success = false;
                    result.Message = "Invalid argument. Please provide a URL to test.";
                    return result;
                }

                _logger.LogInformation($"Testing HTTP connection to {arguments}");

                // Test HTTP connection using HttpClient
                using (var httpClient = new HttpClient())
                {
                    try
                    {
                        var response = await httpClient.GetAsync(arguments, cancellationToken);
                        result.Success = response.IsSuccessStatusCode;
                        result.Message = $"HTTP connection successful. Status Code: {response.StatusCode}";
                    }
                    catch (HttpRequestException ex)
                    {
                        result.Success = false;
                        result.Message = $"HTTP connection failed. Error: {ex.Message}";
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError($"Error testing HTTP connection: {ex.Message}");
                result.Success = false;
                result.Message = $"Error: {ex.Message}";
            }
            // Return as result with Message and Success set.
            return result;
        }

        // Return help on using the cmd procesor as a string.
        public override string GetCommandHelp()
        {
            return @"This command tests an HTTP connection to a given URL.

Usage:
    <URL>

Example:
    https://www.example.com";
        }
    }
}