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
using System.Diagnostics;
using System.Collections.Generic;

namespace NetworkMonitor.Processor
{
    class Program
    {
#pragma warning disable CS8618
        private static ConnectFactory _connectFactory;
        private static ICmdProcessorProvider _cmdProcessorProvider;
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



            string appDataDirectory;

            if (Environment.GetEnvironmentVariable("DOTNET_RUNNING_IN_CONTAINER") == "true")
            {
                // Set your custom directory for the Docker environment
                appDataDirectory = "";
            }
            else
            {
                // Fallback to the regular path on non-containerized environments
                appDataDirectory = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            }

            var netConfig = new NetConnectConfig(config, appDataDirectory);
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
            var logger = loggerFactory.CreateLogger<Program>();
            FileRepo fileRepo;
            if (Directory.Exists("./state"))
            {
                fileRepo = new FileRepo(true, "./state");
                if (!File.Exists("./state/ProcessorDataObj"))
                {
                    File.Create("./state/ProcessorDataObj").Close();
                    fileRepo.SaveStateStringJsonZ<ProcessorDataObj>("ProcessorDataObj", new ProcessorDataObj());
                }
                if (!File.Exists("./state/MonitorIPs"))
                {
                    File.Create("./state/MonitorIPs").Close();
                    fileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", new List<MonitorIP>());

                }
                if (!File.Exists("./state/PingParams"))
                {
                    File.Create("./state/PingParams").Close();
                    fileRepo.SaveStateJsonZ<PingParams>("PingParams", new PingParams());

                }
            }
            else
            {
                fileRepo = new FileRepo();
                if (!File.Exists("ProcessorDataObj"))
                {
                    File.Create("ProcessorDataObj").Close();
                    fileRepo.SaveStateJsonZ<ProcessorDataObj>("ProcessorDataObj", new ProcessorDataObj());
                }
                if (!File.Exists("MonitorIPs"))
                {
                    File.Create("MonitorIPs").Close();
                    fileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", new List<MonitorIP>());

                }
                if (!File.Exists("PingParams"))
                {
                    File.Create("PingParams").Close();
                    fileRepo.SaveStateJsonZ<PingParams>("PingParams", new PingParams());

                }
            }
            var processorStates = new LocalProcessorStates();
            IRabbitRepo rabbitRepo = new RabbitRepo(loggerFactory.CreateLogger<RabbitRepo>(), netConfig);
            await rabbitRepo.ConnectAndSetUp();  
            _cmdProcessorProvider = new CmdProcessorFactory(loggerFactory, rabbitRepo, netConfig);
            _connectFactory = new NetworkMonitor.Connection.ConnectFactory(loggerFactory.CreateLogger<ConnectFactory>(), netConfig: netConfig, cmdProcessorProvider : _cmdProcessorProvider);
           _ = _connectFactory.SetupChromium(netConfig);
            //ISystemParamsHelper systemParamsHelper = new SystemParamsHelper(config, loggerFactory.CreateLogger<SystemParamsHelper>());
            // _connectFactory = new NetworkMonitor.Connection.ConnectFactory(loggerFactory.CreateLogger<ConnectFactory>(), oqsProviderPath: netConfig.OqsProviderPath);
            _monitorPingProcessor = new MonitorPingProcessor(loggerFactory.CreateLogger<MonitorPingProcessor>(), netConfig, _connectFactory, fileRepo, rabbitRepo, processorStates);
            IRabbitListener rabbitListener = new RabbitListener(_monitorPingProcessor, loggerFactory.CreateLogger<RabbitListener>(), netConfig, processorStates, _cmdProcessorProvider);
            AuthService authService;
            var resultListener = rabbitListener.SetupListener();
            var result = await _monitorPingProcessor.Init(new ProcessorInitObj());
            processorStates.IsSetup = result.Success;
            if (config["AuthDevice"] == "true")
            {
                authService = new AuthService(loggerFactory.CreateLogger<AuthService>(), netConfig, rabbitRepo, processorStates);
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
