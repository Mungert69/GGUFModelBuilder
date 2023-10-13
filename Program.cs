using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects.Factory;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Utils.Helpers;
using MetroLog;

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
            string logLevelConfig = config["Logging:LogLevel:Default"];
            LogLevel defaultLogLevel;
            INetLoggerFactory loggerFactory;

            if (Enum.TryParse(logLevelConfig, true, out defaultLogLevel))
            {
                // Successfully converted to LogLevel enum
                  loggerFactory= new NetLoggerFactory(defaultLogLevel);
            }
            else
            {
                // Failed to convert, handle error or provide a default log level
                // For example, use LogLevel.Debug as a default
                loggerFactory = new NetLoggerFactory();
            }
            var fileRepo = new FileRepo();
            ISystemParamsHelper systemParamsHelper = new SystemParamsHelper(config, loggerFactory);
            IRabbitRepo rabbitRepo = new RabbitRepo(loggerFactory, systemParamsHelper);
            _connectFactory = new NetworkMonitor.Connection.ConnectFactory(config, loggerFactory.GetLogger("ConnectFactory"));
            _monitorPingProcessor = new MonitorPingProcessor(config, loggerFactory, _connectFactory, fileRepo, rabbitRepo);
            IRabbitListener rabbitListener = new RabbitListener(_monitorPingProcessor, loggerFactory, systemParamsHelper);

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
