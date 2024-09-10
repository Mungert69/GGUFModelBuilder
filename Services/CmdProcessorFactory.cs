using System;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Connection;
using NetworkMonitor.Processor.Services;
namespace NetworkMonitor.Processor.Services
{
    public interface ICmdProcessorProvider
    {
        ICmdProcessor GetNmapProcessor();
        ICmdProcessor GetMetasploitProcessor();
        ICmdProcessor GetOpensslProcessor();
        ILocalCmdProcessorStates NmapStates { get; }

        ILocalCmdProcessorStates MetasploitStates  { get; }

        ILocalCmdProcessorStates OpensslStates  { get; }
    }

    public class CmdProcessorFactory : ICmdProcessorProvider
    {
        private readonly ILoggerFactory _loggerFactory;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;

        private readonly ILocalCmdProcessorStates _nmapStates;
        private readonly ILocalCmdProcessorStates _metasploitStates;
        private readonly ILocalCmdProcessorStates _opensslStates;

        private ICmdProcessor _nmapProcessor;
        private ICmdProcessor _metasploitProcessor;
        private ICmdProcessor _opensslProcessor;

        public ILocalCmdProcessorStates NmapStates => _nmapStates;

        public ILocalCmdProcessorStates MetasploitStates => _metasploitStates;

        public ILocalCmdProcessorStates OpensslStates => _opensslStates;

        public CmdProcessorFactory(ILoggerFactory loggerFactory, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
            : this(loggerFactory, rabbitRepo, netConfig,
                   new LocalNmapCmdProcessorStates(),
                   new LocalMetaCmdProcessorStates(),
                   new LocalOpensslCmdProcessorStates())
        {
          
        }
        public CmdProcessorFactory(
            ILoggerFactory loggerFactory,
            IRabbitRepo rabbitRepo,
            NetConnectConfig netConfig,
            ILocalCmdProcessorStates nmapStates,
            ILocalCmdProcessorStates metasploitStates,
            ILocalCmdProcessorStates opensslStates)
        {
            _loggerFactory = loggerFactory;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _nmapStates = nmapStates;
            _metasploitStates = metasploitStates;
            _opensslStates = opensslStates;

            // Create processors
            _nmapProcessor = CreateProcessor("nmap");
            _metasploitProcessor = CreateProcessor("metasploit");
            _opensslProcessor = CreateProcessor("openssl");
        }

        public ICmdProcessor GetNmapProcessor() => _nmapProcessor;
        public ICmdProcessor GetMetasploitProcessor() => _metasploitProcessor;
        public ICmdProcessor GetOpensslProcessor() => _opensslProcessor;

        private ICmdProcessor CreateProcessor(string processorType)
        {
            switch (processorType.ToLower())
            {
                case "nmap":
                    return new NmapCmdProcessor(
                        _loggerFactory.CreateLogger<NmapCmdProcessor>(),
                        NmapStates,
                        _rabbitRepo,
                        _netConfig
                    );

                case "metasploit":
                    return new MetaCmdProcessor(
                        _loggerFactory.CreateLogger<MetaCmdProcessor>(),
                        MetasploitStates,
                        _rabbitRepo,
                        _netConfig
                    );

                case "openssl":
                    return new OpensslCmdProcessor(
                        _loggerFactory.CreateLogger<OpensslCmdProcessor>(),
                        OpensslStates,
                        _rabbitRepo,
                        _netConfig
                    );

                default:
                    throw new ArgumentException($"Unsupported processor type: {processorType}");
            }
        }
    }
}

