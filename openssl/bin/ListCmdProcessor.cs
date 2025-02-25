using System; // Required base functionality
using System.Text; // For StringBuilder
using System.Collections.Generic; // For collections
using System.Diagnostics; // For Process execution
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
using System.Net; // For Network operations

namespace NetworkMonitor.Connection
{
    public class ListCmdProcessor : CmdProcessor
    {
        public ListCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig) 
            : base(logger, cmdProcessorStates, rabbitRepo, netConfig) {}

        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result = new ResultObj();
            string output = "";
            try
            {
                // Check if the command is available
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    var warningMessage = $"{_cmdProcessorStates.CmdDisplayName} is not available on this agent.";
                    LogErrorToFile(warningMessage);
                    _logger.LogWarning(warningMessage);
                    output = $"{_cmdProcessorStates.CmdDisplayName} is not available.\n";
                    result.Message = await SendMessage(output, processorScanDataObj);
                    result.Success = false;
                    return result;
                }

                // Execute the 'ls' command
                using (var process = new Process())
                {
                    process.StartInfo.FileName = "ls";
                    process.StartInfo.Arguments = arguments;
                    process.StartInfo.UseShellExecute = false;
                    process.StartInfo.RedirectStandardOutput = true;
                    process.StartInfo.RedirectStandardError = true;
                    process.StartInfo.CreateNoWindow = true;
                    process.StartInfo.WorkingDirectory = _rootFolder;

                    var outputBuilder = new StringBuilder();
                    process.OutputDataReceived += (sender, e) => { if (e.Data != null) outputBuilder.AppendLine(e.Data); };

                    process.Start();
                    process.BeginOutputReadLine();
                    await process.WaitForExitAsync(cancellationToken);

                    output = outputBuilder.ToString();
                    result.Success = true;
                }
            }
            catch (Exception e)
            {
                var errorMessage = $"Error in RunCommand: {e.Message}";
                LogErrorToFile(errorMessage);
                _logger.LogError(errorMessage);
                result.Success = false;
                result.Message = errorMessage;
            }
            return result;
        }

        public override string GetCommandHelp()
        {
    return @"
This command runs the Unix 'ls' command to list directory contents. 
You can provide additional arguments to customize the command. 
For example, '-l' lists details in a long format. 

### Error Logging ###
If an error occurs during command execution, it is logged to a dedicated log file.
Log files are located in the 'logs' directory under the root folder (_rootFolder) and 
are named '<ClassName>.log'. For example, errors from this processor are logged to 'ListCmdProcessor.log'.

Usage:
    arguments: A string containing valid 'ls' command arguments.

Examples:
    - No arguments: Executes 'ls' to list files in the current directory.
    - With arguments: 'ls -l' for detailed output, 'ls -a' to include hidden files.
";
        }

        private void LogErrorToFile(string errorMessage)
        {
            try
            {
                // Ensure the _rootFolder directory exists
                if (string.IsNullOrEmpty(_rootFolder))
                {
                    _logger.LogError("Error: _rootFolder is not set.");
                    return;
                }

                var logDirectory = Path.Combine(_rootFolder, "logs");
                Directory.CreateDirectory(logDirectory); // Create directory if it doesn't exist

                var logFilePath = Path.Combine(logDirectory, $"{GetType().Name}.log");
                var logMessage = $"{DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} - {errorMessage}\n";

                File.AppendAllText(logFilePath, logMessage); // Append the error message to the log file
            }
            catch (Exception ex)
            {
                _logger.LogError($"Failed to write to error log file: {ex.Message}");
            }
        }
    }
}

