using System;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Connection;
using Microsoft.Extensions.Logging;
namespace NetworkMonitor.Processor
{
    class Program
    {
        static void Main(string[] args)
        {
            IConfiguration config = new ConfigurationBuilder()
    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
    .AddEnvironmentVariables()
    .AddCommandLine(args)
    .Build();
            var loggerFactory = LoggerFactory.Create(builder =>
                    {
                        builder
                            .AddFilter("Microsoft", LogLevel.Warning)
                            .AddFilter("System", LogLevel.Warning)
                            .AddFilter("LoggingConsoleApp.Program", LogLevel.Debug)
                            .AddConsole();
                    });
            ILogger<MonitorPingProcessor> logger = loggerFactory.CreateLogger<MonitorPingProcessor>();
            var connectFactory = new ConnectFactory();
            var _monitorPingProcessor = new MonitorPingProcessor(config, logger, connectFactory);
            Console.WriteLine(" Press [enter] to exit.");
            Console.ReadLine();
        }
    }
}
