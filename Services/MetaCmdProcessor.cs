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
    public class MetaCmdProcessor : ICmdProcessor
    {
        private readonly ILogger _logger;
        private readonly ILocalCmdProcessorStates _cmdProcessorStates;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;
        private CancellationTokenSource _cancellationTokenSource;

        public bool UseDefaultEndpoint { get => _cmdProcessorStates.UseDefaultEndpointType; set => _cmdProcessorStates.UseDefaultEndpointType = value; }

        public MetaCmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _logger = logger;
            _cmdProcessorStates = cmdProcessorStates;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;

        }

        public void Dispose()
        {

            _cancellationTokenSource?.Dispose();
        }

        public Task Scan()
        {
            return Task.CompletedTask;
        }

        public async Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null)
        {
            string output = "";
            try
            {
                _cmdProcessorStates.IsRunning = true;


                string message = $"Running Metasploit with arguments {arguments}";
                _logger.LogInformation(message);
                _cmdProcessorStates.RunningMessage += $"{message}\n";

                output = await ExecuteMetasploit(arguments, cancellationToken, processorScanDataObj);

                _logger.LogInformation("Metasploit module execution completed.");
                _cmdProcessorStates.CompletedMessage += "Metasploit module execution completed successfully.\n";

                // Process the output (if any additional processing is needed)
                ProcessMetasploitOutput(output);

                _cmdProcessorStates.IsSuccess = true;
            }
            catch (OperationCanceledException)
            {
                _logger.LogInformation("Metasploit module execution was cancelled.");
                _cmdProcessorStates.CompletedMessage += "Metasploit module execution was cancelled.\n";
                _cmdProcessorStates.IsSuccess = false;
            }
            catch (Exception e)
            {
                _logger.LogError($"Error during Metasploit module execution: {e.Message}");
                _cmdProcessorStates.CompletedMessage += $"Error during Metasploit module execution: {e.Message}\n";
                _cmdProcessorStates.IsSuccess = false;
            }
            finally
            {
                _cmdProcessorStates.IsRunning = false;
            }
            return output;
        }

        private async Task<string> ExecuteMetasploit(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj)
        {
            //string msfconsolePath = _netConfig.MsfconsolePath;

            using (var process = new Process())
            {
                process.StartInfo.FileName = "msfconsole"; // Path to the Metasploit console executable
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
                    await process.WaitForExitAsync().ConfigureAwait(false);
                    cancellationToken.ThrowIfCancellationRequested();
                    if (processorScanDataObj != null)
                    {
                        try
                        {
                            processorScanDataObj.ScanCommandOutput = output.Replace("\n", " ");
                            await _rabbitRepo.PublishAsync<ProcessorScanDataObj>(processorScanDataObj.CallingService, processorScanDataObj);

                        }

                        catch (Exception e)
                        {
                            output = $"Error during publish meta command output: {e.Message}";
                            _logger.LogError(output);

                        }
                    }
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

        private async Task CancelScan()
        {
            if (_cmdProcessorStates.IsRunning && _cancellationTokenSource != null)
            {
                _logger.LogInformation("Cancelling the ongoing Metasploit execution.");
                _cmdProcessorStates.RunningMessage += "Cancelling the ongoing Metasploit execution...\n";
                _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation("No Metasploit execution is currently running.");
                _cmdProcessorStates.CompletedMessage += "No Metasploit execution is currently running.\n";
            }
        }
    }
}
