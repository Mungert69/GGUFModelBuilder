using System;
using System.IO;
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
#pragma warning disable CS8618
        private static ConnectFactory _connectFactory;
        private static MonitorPingProcessor _monitorPingProcessor;
#pragma warning restore CS8618

        static async Task Main(string[] args)
        {
            Console.WriteLine("Start");
            IConfiguration config;
            string stateDirAppSettings = "./state/appsettings.json";

            if (File.Exists(stateDirAppSettings))
            {
                // Use the appsettings.json from the state directory
                config = new ConfigurationBuilder()
                    .AddJsonFile(stateDirAppSettings, optional: false, reloadOnChange: false)
                    .AddEnvironmentVariables()
                    .AddCommandLine(args)
                    .Build();
            }
            else
            {
                // Use the default appsettings.json
                config = new ConfigurationBuilder()
                    .AddJsonFile("appsettings.json", optional: false, reloadOnChange: false)
                    .AddEnvironmentVariables()
                    .AddCommandLine(args)
                    .Build();
            }




            var netConfig = new NetConnectConfig(config);
            using var loggerFactory = LoggerFactory.Create(builder =>
                  {
                      builder
                            .AddFilter("Microsoft", LogLevel.Information)  // Log only warnings from Microsoft namespaces
                            .AddFilter("System", LogLevel.Information)     // Log only warnings from System namespaces
                            .AddFilter("Program", LogLevel.Debug)      // Log all messages from Program class
                                                                       //.AddFilter("NetworkMonitor.Connection", LogLevel.Debug)
                            .AddSimpleConsole(options =>
                        {
                            options.TimestampFormat = "yyyy-MM-dd HH:mm:ss ";
                            options.IncludeScopes = true;
                        });
                  });
            FileRepo fileRepo;
            if (Directory.Exists("./state"))
            {
                fileRepo = new FileRepo(true, "./state");
                if (!File.Exists("./state/ProcessorDataObj")) File.Create("./state/ProcessorDataObj");
                if (!File.Exists("./state/MonitorIPs")) File.Create("./state/MonitorIPs");
                if (!File.Exists("./state/PingParams")) File.Create("./state/PingParams");
            }
            else
            {
                fileRepo = new FileRepo();
            }
            //ISystemParamsHelper systemParamsHelper = new SystemParamsHelper(config, loggerFactory.CreateLogger<SystemParamsHelper>());
            IRabbitRepo rabbitRepo = new RabbitRepo(loggerFactory.CreateLogger<RabbitRepo>(), netConfig.LocalSystemUrl);
            _connectFactory = new NetworkMonitor.Connection.ConnectFactory(loggerFactory.CreateLogger<ConnectFactory>(), oqsProviderPath: netConfig.OqsProviderPath);
            _monitorPingProcessor = new MonitorPingProcessor(loggerFactory.CreateLogger<MonitorPingProcessor>(), netConfig, _connectFactory, fileRepo, rabbitRepo);
            IRabbitListener rabbitListener = new RabbitListener(_monitorPingProcessor, loggerFactory.CreateLogger<RabbitListener>(), netConfig);
            AuthService authService;
            await _monitorPingProcessor.Init(new ProcessorInitObj());
            if (config["AuthDevice"] == "true")
            {
                authService = new AuthService(loggerFactory.CreateLogger<AuthService>(), netConfig, rabbitRepo);
                await authService.InitializeAsync();
                await authService.SendAuthRequestAsync();
                await authService.PollForTokenAsync();
            }


            await Task.Delay(-1);

            Console.CancelKeyPress += async (o, e) =>
            {
                Console.WriteLine("Exit");
                await _monitorPingProcessor.OnStoppingAsync();
            };
        }
    }


}
