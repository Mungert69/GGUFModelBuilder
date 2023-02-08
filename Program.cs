using System;
using System.Threading;
using System.Threading.Tasks;
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
                            .AddSimpleConsole(c =>
                            {
                                c.SingleLine = true;
                                c.TimestampFormat = "[HH:mm:ss] ";
                                c.UseUtcTimestamp = true;
                                c.ColorBehavior = Microsoft.Extensions.Logging.Console.LoggerColorBehavior.Enabled;
    
                            });
                    });
            ILogger<MonitorPingProcessor> logger = loggerFactory.CreateLogger<MonitorPingProcessor>();
            var connectFactory = new NetworkMonitor.Connection.ConnectFactory();
            var _monitorPingProcessor = new MonitorPingProcessor(config, logger, connectFactory);

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
