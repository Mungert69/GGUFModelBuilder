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
          
        }
  
        public override async Task<ResultObj> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            var result=new ResultObj();
            string output = "";
            try
            {
                if (!_cmdProcessorStates.IsCmdAvailable)
                {
                    _logger.LogWarning(" Warning : Metasploit is not enabled or installed on this agent.");
                    output = "Metasploit is not available on this agent. Try installing the docker version of the Quantum Secure Agent or select an agent that has Metasploit Enabled.\n";
                    result.Message= await SendMessage(output, processorScanDataObj);
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
                result.Success= false;
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
            //string msfconsolePath = _netConfig.MsfconsolePath;
            using (var process = new Process())
            {
                process.StartInfo.FileName = _cmdProcessorStates.CmdName; // Path to the Metasploit console executable
                process.StartInfo.Arguments = arguments; // Executes the command

                process.StartInfo.UseShellExecute = false;
                process.StartInfo.RedirectStandardOutput = true;
                process.StartInfo.RedirectStandardError = true; // Add this to capture standard error

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
                   string errorOutput = await process.StandardError.ReadToEndAsync().ConfigureAwait(false);

                        if (!string.IsNullOrWhiteSpace(errorOutput))
                        {
                            output = "Error: " + errorOutput + "\n" + output; // Append the error to the output
                        }
                    await process.WaitForExitAsync().ConfigureAwait(false);
                    cancellationToken.ThrowIfCancellationRequested();
                    //return await SendMessage(output, processorScanDataObj);
                    return output;
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
