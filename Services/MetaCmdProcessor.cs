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

namespace NetworkMonitor.Processor.Services
{
    public class MetaCmdProcessor : CmdProcessor
    {
      
     
        public MetaCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
     : base(logger, cmdProcessorStates, rabbitRepo, netConfig) 
        {
            _cmdProcessorStates.CmdName = "msfconsole";
             _cmdProcessorStates.CmdDisplayName = "Metasploit";
        }



      
        public override async Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            string output = "";
            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning(" Warning : Metasploit is not enabled or installed on this agent.");
                    output = "The penetration command is not available on this agent. Try using another agent.\n";
                    _cmdProcessorStates.IsSuccess = false;
                    _cmdProcessorStates.IsRunning = false;
                    return await SendMessage(output, processorScanDataObj);

                }
                _cmdProcessorStates.IsRunning = true;


                string message = $"Running Metasploit with arguments {arguments}";
                _logger.LogInformation(message);
                _cmdProcessorStates.RunningMessage += $"{message}\n";

                output = await ExecuteMetasploit(arguments, cancellationToken, processorScanDataObj);

                _logger.LogInformation("Metasploit module execution completed.");
                _cmdProcessorStates.CompletedMessage += "Metasploit module execution completed successfully.\n";

                // Process the output (if any additional processing is needed)
                ProcessMetasploitOutput(output);

                _cmdProcessorStates.IsCmdSuccess = true;
            }
            catch (OperationCanceledException)
            {
                _logger.LogInformation("Metasploit module execution was cancelled.");
                _cmdProcessorStates.CompletedMessage += "Metasploit module execution was cancelled.\n";
                _cmdProcessorStates.IsCmdSuccess = false;
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during Metasploit module execution: {e.Message}");
                _cmdProcessorStates.CompletedMessage += $"Error during Metasploit module execution: {e.Message}\n";
                _cmdProcessorStates.IsCmdSuccess = false;
            }
            finally
            {
                _cmdProcessorStates.IsCmdRunning = false;
                  return SendMessage(output, processorScanDataObj);
            }
        }

        private async Task<string> ExecuteMetasploit(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj)
        {
            //string msfconsolePath = _netConfig.MsfconsolePath;

            using (var process = new Process())
            {
                process.StartInfo.FileName = _cmdProcessorStates.CmdName; // Path to the Metasploit console executable
                process.StartInfo.Arguments = arguments; // Executes the command

                process.StartInfo.UseShellExecute = false;
                process.StartInfo.RedirectStandardOutput = true;
                process.StartInfo.CreateNoWindow = true;

                process.Start();

                using (cancellationToken.Register(() =>
                {
                    if (!process.HasExited)
                    {
                        _logger.LogInformation("Cancellation requested, killing the Metasploit process...");
                        process.Kill();
                    }
                }))
                {
                    string output = await process.StandardOutput.ReadToEndAsync().ConfigureAwait(false);
                    //output += " "+ await process.StandardError.ReadToEndAsync().ConfigureAwait(false);

                    await process.WaitForExitAsync().ConfigureAwait(false);
                    cancellationToken.ThrowIfCancellationRequested();
                    return await SendMessage(output, processorScanDataObj);
                }
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
