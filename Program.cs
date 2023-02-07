using System;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Connection;
using Microsoft.Extensions.Logging;
namespace NetworkMonitor.Processor
{
    class Program
    {
        private static readonly AutoResetEvent waitHandle = new AutoResetEvent(false);
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
            //var _monitorPingProcessor = new MonitorPingProcessor(config, logger, connectFactory);
            Task.Run(() =>
            {
                var random = new Random(10);
                while (true)
                {
                    // Write here whatever your side car applications needs to do.
                    // In this sample we are just writing a random number to the Console (stdout)
                    Console.WriteLine($"Loop = {random.Next()}");
                    // Sleep as long as you need.
                    Thread.Sleep(1000);
                }
            });
            // Handle Control+C or Control+Break
            Console.CancelKeyPress += (o, e) =>
            {
                Console.WriteLine("Exit");
                // Allow the manin thread to continue and exit...
                waitHandle.Set();
            };
            // Wait
            waitHandle.WaitOne();
        }
    }
}
