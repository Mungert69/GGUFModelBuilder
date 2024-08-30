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

        public abstract async Task Scan();

        public abstract async Task AddServices();

        public abstract async Task CancelScan();

        public abstract async Task CancelRun();


        public abstract async Task<string> RunCommand(string arguments, CancellationToken cancellationToken, ProcessorScanDataObj? processorScanDataObj = null);
      

        protected virtual async Task<string> SendMessage(string output, ProcessorScanDataObj? processorScanDataObj)
        {
            if (processorScanDataObj == null) return output;
            else
            {
                try
                {
                    processorScanDataObj.ScanCommandOutput = output.Replace("\n", " ");
                    await _rabbitRepo.PublishAsync<ProcessorScanDataObj>(processorScanDataObj.CallingService, processorScanDataObj);
                    _logger.LogInformation($" Success : sent output : {processorScanDataObj.ScanCommandOutput}");
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