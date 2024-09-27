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
        ICmdProcessor GetBusyboxProcessor();
        ICmdProcessor GetSearchWebProcessor();
        ICmdProcessor GetCrawlPageProcessor();
        ICmdProcessor GetPingProcessor();
        ILocalCmdProcessorStates NmapStates { get; }

        ILocalCmdProcessorStates MetasploitStates { get; }

        ILocalCmdProcessorStates OpensslStates { get; }
        ILocalCmdProcessorStates BusyboxStates { get; }
        ILocalCmdProcessorStates SearchWebStates { get; }
        ILocalCmdProcessorStates CrawlPageStates { get; }
        ILocalCmdProcessorStates PingStates { get; }
    }

    public class CmdProcessorFactory : ICmdProcessorProvider
    {
        private readonly ILoggerFactory _loggerFactory;
        private readonly IRabbitRepo _rabbitRepo;
        private readonly NetConnectConfig _netConfig;

        private readonly ILocalCmdProcessorStates _nmapStates;
        private readonly ILocalCmdProcessorStates _metasploitStates;
        private readonly ILocalCmdProcessorStates _opensslStates;
        private readonly ILocalCmdProcessorStates _busyboxStates;
        private readonly ILocalCmdProcessorStates _searchwebStates;
        private readonly ILocalCmdProcessorStates _crawlpageStates;
        private readonly ILocalCmdProcessorStates _pingStates;

        private ICmdProcessor _nmapProcessor;
        private ICmdProcessor _metasploitProcessor;
        private ICmdProcessor _opensslProcessor;
        private ICmdProcessor _busyboxProcessor;
        private ICmdProcessor _searchwebProcessor;
        private ICmdProcessor _crawlpageProcessor;
        private ICmdProcessor _pingProcessor;

        public ILocalCmdProcessorStates NmapStates => _nmapStates;
        public ILocalCmdProcessorStates MetasploitStates => _metasploitStates;
        public ILocalCmdProcessorStates OpensslStates => _opensslStates;
        public ILocalCmdProcessorStates BusyboxStates => _busyboxStates;
        public ILocalCmdProcessorStates SearchWebStates => _searchwebStates;
        public ILocalCmdProcessorStates CrawlPageStates => _crawlpageStates;
        public ILocalCmdProcessorStates PingStates => _pingStates;

        public CmdProcessorFactory(ILoggerFactory loggerFactory, IRabbitRepo rabbitRepo, NetConnectConfig netConfig)
            : this(loggerFactory, rabbitRepo, netConfig,
                   new LocalNmapCmdProcessorStates(),
                   new LocalMetaCmdProcessorStates(),
                   new LocalOpensslCmdProcessorStates(),
                   new LocalBusyboxCmdProcessorStates(),
                   new LocalSearchWebCmdProcessorStates(),
                   new LocalCrawlPageCmdProcessorStates(),
                   new LocalPingCmdProcessorStates()
                   )
        {

        }
        public CmdProcessorFactory(
            ILoggerFactory loggerFactory,
            IRabbitRepo rabbitRepo,
            NetConnectConfig netConfig,
            ILocalCmdProcessorStates nmapStates,
            ILocalCmdProcessorStates metasploitStates,
            ILocalCmdProcessorStates opensslStates,
            ILocalCmdProcessorStates busyboxStates,
            ILocalCmdProcessorStates searchwebStates,
            ILocalCmdProcessorStates crawlpageStates,
               ILocalCmdProcessorStates pingStates
            )
        {
            _loggerFactory = loggerFactory;
            _rabbitRepo = rabbitRepo;
            _netConfig = netConfig;
            _nmapStates = nmapStates;
            _metasploitStates = metasploitStates;
            _opensslStates = opensslStates;
            _busyboxStates = busyboxStates;
            _searchwebStates = searchwebStates;
            _crawlpageStates = crawlpageStates;
            _pingStates = pingStates;

            // Create processors
            _nmapProcessor = CreateProcessor("nmap");
            _metasploitProcessor = CreateProcessor("metasploit");
            _opensslProcessor = CreateProcessor("openssl");
            _busyboxProcessor = CreateProcessor("busybox");
            _searchwebProcessor = CreateProcessor("searchweb");
            _crawlpageProcessor = CreateProcessor("crawlpage");
            _pingProcessor = CreateProcessor("ping");
        }

        public ICmdProcessor GetNmapProcessor() => _nmapProcessor;
        public ICmdProcessor GetMetasploitProcessor() => _metasploitProcessor;
        public ICmdProcessor GetOpensslProcessor() => _opensslProcessor;
        public ICmdProcessor GetBusyboxProcessor() => _busyboxProcessor;
        public ICmdProcessor GetSearchWebProcessor() => _searchwebProcessor;
        public ICmdProcessor GetCrawlPageProcessor() => _crawlpageProcessor;
        public ICmdProcessor GetPingProcessor() => _pingProcessor;


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
                case "busybox":
                    return new BusyboxCmdProcessor(
                        _loggerFactory.CreateLogger<BusyboxCmdProcessor>(),
                        BusyboxStates,
                        _rabbitRepo,
                        _netConfig
                    );
                case "searchweb":
                    return new SearchWebCmdProcessor(
                        _loggerFactory.CreateLogger<SearchWebCmdProcessor>(),
                        SearchWebStates,
                        _rabbitRepo,
                        _netConfig
                    );
                case "crawlpage":
                    return new CrawlPageCmdProcessor(
                        _loggerFactory.CreateLogger<CrawlPageCmdProcessor>(),
                        CrawlPageStates,
                        _rabbitRepo,
                        _netConfig
                    );
                case "ping":
                    return new PingCmdProcessor(
                        _loggerFactory.CreateLogger<PingCmdProcessor>(),
                        PingStates,
                        _rabbitRepo,
                        _netConfig);

                default:
                    throw new ArgumentException($"Unsupported processor type: {processorType}");
            }
        }
    }
}

