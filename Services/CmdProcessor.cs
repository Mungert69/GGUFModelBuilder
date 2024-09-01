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

namespace NetworkMonitor.Processor.Services
{
    public interface ICmdProcessor : IDisposable
    {
        Task Scan();
        Task CancelScan();
        Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null);
        Task CancelRun();
        bool UseDefaultEndpoint { get; set; }
    }
    public abstract class CmdProcessor : ICmdProcessor
    {
        protected readonly ILogger _logger;
        protected readonly ILocalCmdProcessorStates _cmdProcessorStates;
        protected readonly IRabbitRepo _rabbitRepo;
        protected readonly NetConnectConfig _netConfig;
        protected CancellationTokenSource _cancellationTokenSource;

        public bool UseDefaultEndpoint { get => _cmdProcessorStates.UseDefaultEndpointType; set => _cmdProcessorStates.UseDefaultEndpointType = value; }
        public CmdProcessor(ILogger logger, ILocalCmdProcessorStates cmdProcessorStates, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _logger = logger;
            _cmdProcessorStates = cmdProcessorStates;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _cmdProcessorStates.OnStartScanAsync += Scan;
            _cmdProcessorStates.OnCancelScanAsync += CancelScan;
            _cmdProcessorStates.OnAddServicesAsync += AddServices;

        }

        public virtual void Dispose()
        {
            _cmdProcessorStates.OnStartScanAsync -= Scan;
            _cmdProcessorStates.OnCancelScanAsync -= CancelScan;
            _cmdProcessorStates.OnAddServicesAsync -= AddServices;
            _cancellationTokenSource?.Dispose();
        }

        public virtual async Task Scan()
        {

            _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName} Scan Command is not enabled or installed on this agent.");
            var output = $"The {_cmdProcessorStates.CmdDisplayName}  Scan Command is not available on this agent. Try using another agent.\n";
            _cmdProcessorStates.IsSuccess = false;
            _cmdProcessorStates.IsRunning = false;
            await SendMessage(output, null);



        }

        public virtual async Task AddServices()
        {
            _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName} Add Services command is not enabled or installed on this agent.");
            var output = $"{_cmdProcessorStates.CmdDisplayName} Add Services command is not available on this agent. Try using another agent.\n";
            _cmdProcessorStates.IsSuccess = false;
            _cmdProcessorStates.IsRunning = false;
            await SendMessage(output, null);
        }

        public virtual async Task CancelScan()
        {
            if (!_cmdProcessorStates.IsCmdAvailable)
            {
                _logger.LogWarning($" Warning : {_cmdProcessorStates.CmdName} command is not enabled or installed on this agent.");
                var output = $"The {_cmdProcessorStates.CmdDisplayName} command is not available on this agent. Try using another agent.\n";
                _cmdProcessorStates.IsSuccess = false;
                _cmdProcessorStates.IsRunning = false;
                await SendMessage(output, null);
                return;

            }
            if (_cmdProcessorStates.IsRunning && _cancellationTokenSource != null)
            {
                _logger.LogWarning($" Warning : Cancelling the ongoing {_cmdProcessorStates.CmdName} scan.");
                _cmdProcessorStates.RunningMessage += $"Cancelling the ongoing {_cmdProcessorStates.CmdDisplayName} scan...\n";
                if (_cancellationTokenSource != null) _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation($"No {_cmdProcessorStates.CmdName} scan is currently running.");
                _cmdProcessorStates.CompletedMessage += $"No {_cmdProcessorStates.CmdDisplayName} scan is currently running.\n";
            }
        }




        public abstract Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null);


        public virtual async Task CancelRun()
        {
            if (_cmdProcessorStates.IsCmdRunning && _cancellationTokenSource != null)
            {
                _logger.LogInformation($"Cancelling the ongoing {_cmdProcessorStates.CmdName} execution.");
                _cmdProcessorStates.RunningMessage += $"Cancelling the ongoing {_cmdProcessorStates.CmdDisplayName} execution...\n";
                _cancellationTokenSource.Cancel();
            }
            else
            {
                _logger.LogInformation($"No {_cmdProcessorStates.CmdName} execution is currently running.");
                _cmdProcessorStates.CompletedMessage += $"No {_cmdProcessorStates.CmdName} execution is currently running.\n";
            }
        }
        protected virtual async Task<string> SendMessage(string output, ProcessorScanDataObj? processorScanDataObj)
        {
            if (processorScanDataObj == null) return output;
            else
            {
                try
                {
                    if (processorScanDataObj.LineLimit == -1)
                    {
                        // Default to 100 lines if LineLimit is -1
                        processorScanDataObj.LineLimit = _netConfig.CmdReturnDataLineLimit;
                    }

                    var lines = output.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);

                    if (lines.Length > processorScanDataObj.LineLimit)
                    {
                        // Truncate output if there are more lines than the limit
                        output = string.Join(Environment.NewLine, lines.Take(processorScanDataObj.LineLimit));

                        // Append a message indicating truncation and advice
                        output += Environment.NewLine + $"[Output truncated to the first {processorScanDataObj.LineLimit} lines. Consider setting number_lines higher if you want more data or refining your query to return more targetted data.]";
                    }

                    processorScanDataObj.ScanCommandOutput = output;
                    await _rabbitRepo.PublishAsync<ProcessorScanDataObj>(processorScanDataObj.CallingService, processorScanDataObj);
                    _logger.LogInformation($" Success : sending with MessageID {processorScanDataObj.MessageID} output : {processorScanDataObj.ScanCommandOutput}");
                }

                catch (Exception e)
                {
                    output += $" Error : during publish {_cmdProcessorStates.CmdName} command output: {e.Message}";
                    _logger.LogError(output);

                }
                return output;


            }
        }

    }





}