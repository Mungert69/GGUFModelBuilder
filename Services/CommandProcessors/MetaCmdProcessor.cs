using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using System.Runtime.InteropServices;
using System.Linq;
using System.Text;

namespace NetworkMonitor.Processor.Services
{
    public class MetaCmdProcessor : CmdProcessor
    {


        public MetaCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
     : base(logger, cmdProcessorStates, rabbitRepo, netConfig)
        {

        }

        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result = new ResultObj();
            string output = "";
            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning(" Warning : Metasploit is not enabled or installed on this agent.");
                    output = "Metasploit is not available on this agent. Try installing the docker version of the Quantum Secure Agent or select an agent that has Metasploit Enabled.\n";
                    result.Message = await SendMessage(output, processorScanDataObj);
                    result.Success = false;
                    return result;

                }

                string message = $"Running Metasploit with arguments {arguments}";
                _logger.LogInformation(message);
                _cmdProcessorStates.RunningMessage += $"{message}\n";

                output = await ExecuteMetasploit(arguments, cancellationToken, processorScanDataObj);

                _logger.LogInformation("Metasploit module execution completed.");
                _cmdProcessorStates.CompletedMessage += "Metasploit module execution completed successfully.\n";

                // Process the output (if any additional processing is needed)
                ProcessMetasploitOutput(output);
                result.Message += output;

            }
            catch (OperationCanceledException)
            {
                _logger.LogInformation("Metasploit module execution was cancelled.");
                _cmdProcessorStates.CompletedMessage += "Metasploit module execution was cancelled.\n";
                result.Message += _cmdProcessorStates.CompletedMessage;
                result.Success = false;
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during Metasploit module execution: {e.Message}");
                _cmdProcessorStates.CompletedMessage += $"Error during Metasploit module execution: {e.Message}\n";
                result.Success = false;
                result.Message += _cmdProcessorStates.CompletedMessage;
            }

            return result;
        }

        private async Task<string> ExecuteMetasploit(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj)
        {
            string msfDir = "";
            string msfPath = _cmdProcessorStates.CmdName;
            string output = "";
            // Use 'where' command to locate the executable in the system's PATH
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                msfDir = await FindExecutableDirectoryInPath(_cmdProcessorStates.CmdName);
                msfPath = Path.Combine(msfDir, _cmdProcessorStates.CmdName) + ".bat";
                if (string.IsNullOrEmpty(msfDir))
                {
                    throw new FileNotFoundException($"Metasploit executable {_cmdProcessorStates.CmdName} not found in system PATH.");
                }
            }

            //string msfconsolePath = _netConfig.MsfconsolePath;
            using (var process = new Process())
            {
                process.StartInfo.FileName = msfPath;// Path to the Metasploit console executable
                process.StartInfo.Arguments = arguments; // Executes the command

                process.StartInfo.UseShellExecute = false;
                process.StartInfo.RedirectStandardOutput = true;
                process.StartInfo.RedirectStandardError = true; // Add this to capture standard error
                process.StartInfo.WorkingDirectory = msfDir;
                process.StartInfo.CreateNoWindow = true;
                var outputBuilder = new StringBuilder();
                var errorBuilder = new StringBuilder();

                process.OutputDataReceived += (sender, e) =>
                {
                    if (e.Data != null)
                    {
                        outputBuilder.AppendLine(e.Data);
                    }
                };

                process.ErrorDataReceived += (sender, e) =>
                {
                    if (e.Data != null)
                    {
                        errorBuilder.AppendLine(e.Data);
                    }
                };

                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();

                using (cancellationToken.Register(() =>
                {
                    if (!process.HasExited)
                    {
                        _logger.LogInformation("Cancellation requested, killing the Metasploit process...");
                        process.Kill();
                    }
                }))
                {
                    await process.WaitForExitAsync(cancellationToken);
                    cancellationToken.ThrowIfCancellationRequested(); // Check if cancelled before processing output

                    output = outputBuilder.ToString();
                    string errorOutput = errorBuilder.ToString();

                    if (!string.IsNullOrWhiteSpace(errorOutput) && processorScanDataObj != null)
                    {
                        output = $"Error: {errorOutput}. \n {output}";
                    }
                    return output;
                }
            }
        }


        private async Task<string> FindExecutableDirectoryInPath(string commandName)
        {
            using (var process = new Process())
            {
                process.StartInfo.FileName = "where";
                process.StartInfo.Arguments = commandName;
                process.StartInfo.UseShellExecute = false;
                process.StartInfo.RedirectStandardOutput = true;
                process.StartInfo.RedirectStandardError = true;
                process.StartInfo.CreateNoWindow = true;

                process.Start();

                string output = await process.StandardOutput.ReadToEndAsync().ConfigureAwait(false);
                string errorOutput = await process.StandardError.ReadToEndAsync().ConfigureAwait(false);

                if (!string.IsNullOrWhiteSpace(errorOutput))
                {
                    _logger.LogError("Error finding executable: " + errorOutput);
                }

                await process.WaitForExitAsync().ConfigureAwait(false);

                // Get the first path found by the 'where' command
                string exePath = output.Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "";

                if (!string.IsNullOrEmpty(exePath))
                {
                    // Return the directory part of the path
                    return Path.GetDirectoryName(exePath) ?? "";
                }

                return ""; // Return empty string if no path is found
            }
        }

        private void ProcessMetasploitOutput(string output)
        {
            // Process the output here if necessary, or log it
            _logger.LogInformation($"Metasploit output: {output}");
            _cmdProcessorStates.CompletedMessage += $"Metasploit output: {output}\n";
        }


    }
}
