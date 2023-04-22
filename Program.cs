using System;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.Factory;

namespace NetworkMonitor.Processor
{
    class Program
    {
     
    private static ConnectFactory _connectFactory ;
    private static MonitorPingProcessor _monitorPingProcessor;

        private static readonly AutoResetEvent waitHandle = new AutoResetEvent(false);
        static void Main(string[] args)
        {
            /*
               var pingParams = new PingParams
            {
                Timeout = 10000
            };
          var pingInfo = new MonitorPingInfo
            {
                MonitorIPID = 1,
                //Address = "pq.cloudflareresearch.com",
                // Address = "google.com",
                Address= "localhost",
                EndPointType = "Quantum",
                PingInfos = new List<PingInfo>(),
                Timeout = 5000
            };
            // Arrange
            var quantumConnect = new QuantumConnect(pingInfo, pingParams);
            quantumConnect.connect();
            */

            
            IConfiguration config = new ConfigurationBuilder()
                 .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
                 .AddEnvironmentVariables()
                 .AddCommandLine(args)
                 .Build();
        var loggerFactory=new NetLoggerFactory();
        _connectFactory = new NetworkMonitor.Connection.ConnectFactory(config);
        _monitorPingProcessor = new MonitorPingProcessor(config, loggerFactory.GetLogger("Processor"), _connectFactory);
      Task.Run(() =>
            {
                while (true)
                {
                    Task.Delay(1000).Wait();
                }
            });
            // Handle Control+C or Control+Break
            Console.CancelKeyPress += (o, e) =>
            {
                Console.WriteLine("Exit");
                _monitorPingProcessor.OnStopping();
                // Allow the manin thread to continue and exit...
                waitHandle.Set();
            };
            // Wait
            waitHandle.WaitOne();
        }
    }
}
