using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects.Factory;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Utils.Helpers;
using Microsoft.Extensions.Logging;

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
             using var loggerFactory = LoggerFactory.Create(builder =>
        {
            builder
                .AddFilter("Microsoft", LogLevel.Warning)  // Log only warnings from Microsoft namespaces
                .AddFilter("System", LogLevel.Warning)     // Log only warnings from System namespaces
                .AddFilter("Program", LogLevel.Debug)      // Log all messages from Program class
                .AddConsole();                             // Add console logger
        });

        var logger = loggerFactory.CreateLogger<Program>();
            
           
            /*if (Enum.TryParse(logLevelConfig, true, out defaultLogLevel))
            {
                // Successfully converted to LogLevel enum
                  loggerFactory= new LoggerFactory();
            }
            else
            {
                // Failed to convert, handle error or provide a default log level
                // For example, use LogLevel.LogDebug as a default
                loggerFactory = new LoggerFactory();
            }*/
            var fileRepo = new FileRepo();
            ISystemParamsHelper systemParamsHelper = new SystemParamsHelper(config, logger);
            IRabbitRepo rabbitRepo = new RabbitRepo(logger, systemParamsHelper);
            _connectFactory = new NetworkMonitor.Connection.ConnectFactory(config, logger);
            _monitorPingProcessor = new MonitorPingProcessor(config, logger, _connectFactory, fileRepo, rabbitRepo);
            IRabbitListener rabbitListener = new RabbitListener(_monitorPingProcessor, logger, systemParamsHelper);

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
