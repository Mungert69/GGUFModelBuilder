using System.Text;
using RabbitMQ.Client;
using RabbitMQ.Client.Events;
using CloudNative.CloudEvents;
using CloudNative.CloudEvents.NewtonsoftJson;
using Newtonsoft.Json.Linq;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Objects.Repository;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Connection;
using Microsoft.Extensions.Logging;

IConfiguration config = new ConfigurationBuilder()
   .AddJsonFile("/home/mahadeva/code/RabbitMQTest/Receive/appsettings.json", optional: false, reloadOnChange: true)
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
