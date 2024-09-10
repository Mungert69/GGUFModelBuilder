using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using NetworkMonitor.Utils;
using System.Xml.Linq;
using System.IO;
using System.Threading;
using NetworkMonitor.Service.Services.OpenAI;

namespace NetworkMonitor.Processor.Services
{
    public class OpensslCmdProcessor : CmdProcessor
    {

        public OpensslCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
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
                    _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdDisplayName} is not enabled or installed on this agent.");
                    output = $"{_cmdProcessorStates.CmdDisplayName} is not available on this agent. Try installing the Quantum Secure Agent or select an agent that has Openssl enabled.\n";
                    result.Message = await SendMessage(output, processorScanDataObj);
                    result.Success = false;
                    return result;

                }
                string nmapPath = "";
                if (!String.IsNullOrEmpty(_netConfig.OqsProviderPath) && !_netConfig.OqsProviderPath.Equals("/usr/local/lib/"))
                {
                    nmapPath = _netConfig.OqsProviderPath.Replace("lib64", "bin");
                    if (!nmapPath.EndsWith(Path.DirectorySeparatorChar.ToString()))
                    {
                        nmapPath += Path.DirectorySeparatorChar;
                    }
                }

                using (var process = new Process())
                {
                    process.StartInfo.FileName = nmapPath + _cmdProcessorStates.CmdName;
                    process.StartInfo.Arguments = arguments;
                    process.StartInfo.UseShellExecute = false;
                    process.StartInfo.RedirectStandardOutput = true;
                    process.StartInfo.RedirectStandardError = true; // Add this to capture standard error
                    process.StartInfo.EnvironmentVariables["LD_LIBRARY_PATH"] = _netConfig.OqsProviderPath;
                    process.StartInfo.CreateNoWindow = true;
                    process.StartInfo.WorkingDirectory = nmapPath;

                    // Start the process
                    process.Start();

                    // Register a callback to kill the process if cancellation is requested
                    using (cancellationToken.Register(() =>
                    {
                        if (!process.HasExited)
                        {
                            _logger.LogInformation($"Cancellation requested, killing the {_cmdProcessorStates.CmdDisplayName} process...");
                            process.Kill();
                        }
                    }))
                    {
                        // Read the output asynchronously, supporting cancellation
                        output = await process.StandardOutput.ReadToEndAsync().ConfigureAwait(false);
                        //output += " "+await process.StandardError.ReadToEndAsync().ConfigureAwait(false);
                        // Capture standard error
                        string errorOutput = await process.StandardError.ReadToEndAsync().ConfigureAwait(false);

                        if (!string.IsNullOrWhiteSpace(errorOutput) && processorScanDataObj != null)
                        {
                            output = "Error: " + errorOutput + "\n" + output; // Append the error to the output
                        }
                        // Wait for the process to exit
                        await process.WaitForExitAsync().ConfigureAwait(false);

                        // Throw if cancellation was requested after the process started
                        cancellationToken.ThrowIfCancellationRequested();
                        result.Success = true;
                    }
                }
            }
            catch (Exception e)
            {
                _logger.LogError($"Error : running {_cmdProcessorStates.CmdName} command. Errro was : {e.Message}");
                output += $"Error : running {_cmdProcessorStates.CmdName} command. Error was : {e.Message}\n";
                result.Success = false;
            }
            result.Message = output;
            return result;
        }

   
    }



}