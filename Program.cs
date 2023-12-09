using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects.Factory;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Processor.Services;
using NetworkMonitor.Utils.Helpers;
using NetworkMonitor.Objects;
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



            var netConfig = new NetConnectConfig(config);
            using var loggerFactory = LoggerFactory.Create(builder =>
                  {
                      builder
                            .AddFilter("Microsoft", LogLevel.Information)  // Log only warnings from Microsoft namespaces
                            .AddFilter("System", LogLevel.Information)     // Log only warnings from System namespaces
                            .AddFilter("Program", LogLevel.Debug)      // Log all messages from Program class
                            .AddConsole();                             // Add console logger
                  });

            var fileRepo = new FileRepo();
            //ISystemParamsHelper systemParamsHelper = new SystemParamsHelper(config, loggerFactory.CreateLogger<SystemParamsHelper>());
            IRabbitRepo rabbitRepo = new RabbitRepo(loggerFactory.CreateLogger<RabbitRepo>(), netConfig.LocalSystemUrl);
            _connectFactory = new NetworkMonitor.Connection.ConnectFactory(loggerFactory.CreateLogger<ConnectFactory>(), oqsProviderPath: netConfig.OqsProviderPath);
            _monitorPingProcessor = new MonitorPingProcessor(loggerFactory.CreateLogger<MonitorPingProcessor>(), netConfig, _connectFactory, fileRepo, rabbitRepo);
            IRabbitListener rabbitListener = new RabbitListener(_monitorPingProcessor, loggerFactory.CreateLogger<RabbitListener>(), netConfig);
            AuthService authService=new AuthService(loggerFactory.CreateLogger<AuthService>(),netConfig);
   
            await _monitorPingProcessor.Init(new ProcessorInitObj());
            await authService.InitializeAsync();
            await authService.ConnectDeviceAsync();
            
            await Task.Delay(-1);

            Console.CancelKeyPress += async (o, e) =>
            {
                Console.WriteLine("Exit");
                await _monitorPingProcessor.OnStoppingAsync();
            };
        }
    }


}
