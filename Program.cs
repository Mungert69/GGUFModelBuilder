using System;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects;
using MetroLog;
using MetroLog.Maui;
using MetroLog.Targets;

namespace NetworkMonitor.Processor
{
    class Program
    {
       private static  ILogger _logger; 
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
          var configLog = new LoggingConfiguration();

#if RELEASE
    config.AddTarget(
        LogLevel.Info, 
        LogLevel.Fatal, 
        new StreamingFileTarget(retainDays: 2);
#else
        // Will write logs to the Debug output
        configLog.AddTarget(
            LogLevel.Trace,
            LogLevel.Fatal,
            new TraceTarget());
#endif

        // will write logs to the console output (Logcat for android)
        configLog.AddTarget(
            LogLevel.Info,
            LogLevel.Fatal,
            new ConsoleTarget());

        configLog.AddTarget(
            LogLevel.Info,
            LogLevel.Fatal,
            new MemoryTarget(2048));

        LoggerFactory.Initialize(configLog);
        _logger = LoggerFactory.GetLogger(nameof(MonitorPingProcessor));
        _connectFactory = new NetworkMonitor.Connection.ConnectFactory();
        _monitorPingProcessor = new MonitorPingProcessor(config, _logger, _connectFactory);
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
