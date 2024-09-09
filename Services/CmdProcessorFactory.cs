using System;
using Microsoft.Extensions.Logging;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Connection;

namespace NetworkMonitor.Processor.Services
{
     public interface ICmdProcessorProvider
    {
        ICmdProcessor GetNmapProcessor();
        ICmdProcessor GetMetasploitProcessor();
        ICmdProcessor GetOpensslProcessor();
    }
    public class CmdProcessorFactory : ICmdProcessorProvider
    {
        private readonly ILoggerFactory _loggerFactory;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;

        private ICmdProcessor _nmapProcessor;
        private ICmdProcessor _metasploitProcessor;
        private ICmdProcessor _opensslProcessor;

        public CmdProcessorFactory(ILoggerFactory loggerFactory, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
        {
            _loggerFactory = loggerFactory;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;

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
                    var nmapStates = new LocalNmapCmdProcessorStates
                    {
                        CmdName = "nmap",
                        CmdDisplayName = "Nmap"
                    };
                    return new NmapCmdProcessor(
                        _loggerFactory.CreateLogger<NmapCmdProcessor>(),
                        nmapStates,
                        _rabbitRepo,
                        _netConfig
                    );

                case "metasploit":
                    var metaStates = new LocalMetaCmdProcessorStates
                    {
                        CmdName = "msfconsole",
                        CmdDisplayName = "Metasploit"
                    };
                    return new MetaCmdProcessor(
                        _loggerFactory.CreateLogger<MetaCmdProcessor>(),
                        metaStates,
                        _rabbitRepo,
                        _netConfig
                    );

                case "openssl":
                    var opensslStates = new LocalOpensslCmdProcessorStates
                    {
                        CmdName = "openssl",
                        CmdDisplayName = "OpenSSL"
                    };
                    return new OpensslCmdProcessor(
                        _loggerFactory.CreateLogger<OpensslCmdProcessor>(),
                        opensslStates,
                        _rabbitRepo,
                        _netConfig
                    );

                default:
                    throw new ArgumentException($"Unsupported processor type: {processorType}");
            }
        }
    }
}