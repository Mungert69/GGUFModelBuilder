using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects.Factory;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Processor.Services;

namespace NetworkMonitor.Processor
{
    class Program
    {
        private static ConnectFactory _connectFactory;
        private static MonitorPingProcessor _monitorPingProcessor;

        static async Task Main(string[] args)
        {
            IConfiguration config = new ConfigurationBuilder()
                 .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
                 .AddEnvironmentVariables()
                 .AddCommandLine(args)
                 .Build();
            var loggerFactory = new NetLoggerFactory();
            _connectFactory = new NetworkMonitor.Connection.ConnectFactory(config,loggerFactory.GetLogger("ConnectFactory"));
            _monitorPingProcessor = new MonitorPingProcessor(config, loggerFactory.GetLogger("Processor"), _connectFactory);
            await _monitorPingProcessor.Init(new ProcessorInitObj());
            await Task.Delay(-1);

            Console.CancelKeyPress += async (o, e) =>
            {
                Console.WriteLine("Exit");
                await _monitorPingProcessor.OnStoppingAsync();
            };
        }
    }
}
