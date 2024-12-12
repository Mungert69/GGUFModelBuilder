using RabbitMQ.Client;
using RabbitMQ.Client.Events;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using NetworkMonitor.Processor.Services;
using System.Collections.Generic;
using System;
using System.Threading.Tasks;
using System.Threading;
using System.Linq;
using NetworkMonitor.Utils;
using NetworkMonitor.Utils.Helpers;
using Microsoft.Extensions.Logging;
namespace NetworkMonitor.Objects.Repository
{
    public interface IRabbitListener
    {
        ResultObj Connect(ProcessorConnectObj connectObj);
        ResultObj RemovePingInfos(ProcessorDataObj processorDataObj);
        Task<ResultObj> Init(ProcessorInitObj initObj);
        ResultObj AlertFlag(List<int> monitorPingInfoIds);
        ResultObj AlertSent(List<int> monitorIPIDs);
        Task<ResultObj> ResetAlerts(List<int> monitorIPIDs);
        ResultObj QueueDic(ProcessorQueueDicObj queueDicObj);
        Task<ResultObj> WakeUp();
        Task<ResultObj> ProcessorUserEvent(ProcessorUserEventObj processorUserEventObj);
        Task Shutdown();
        Task<ResultObj> Setup();
    }
    public class RabbitListener : RabbitListenerBase, IRabbitListener
    {
        //private string _appID;
        private IMonitorPingProcessor _monitorPingProcessor;
        private ICmdProcessorProvider _cmdProcessorProvider;
        private NetConnectConfig _netConfig;
        private System.Timers.Timer _pollingTimer;
        private TimeSpan _pollingInterval = TimeSpan.FromMinutes(1);


        public RabbitListener(IMonitorPingProcessor monitorPingProcessor, ILogger logger, NetConnectConfig netConnectConfig, LocalProcessorStates localProcessorStates, ICmdProcessorProvider cmdProcessorProvider) : base(logger, DeriveSystemUrl(netConnectConfig), localProcessorStates as IRabbitListenerState, netConnectConfig.UseTls)
        {
            _monitorPingProcessor = monitorPingProcessor;
            _cmdProcessorProvider = cmdProcessorProvider;
            //_appID = monitorPingProcessor.AppID;
            _netConfig = netConnectConfig;
            _netConfig.OnSystemUrlChangedAsync += HandleSystemUrlChangedAsync;
            //Setup();
            // Set up the polling timer
            _pollingTimer = new System.Timers.Timer(_pollingInterval.TotalMilliseconds);
            _pollingTimer.Elapsed += async (sender, e) => await PollingTick();
            _pollingTimer.AutoReset = true;
            _pollingTimer.Start();
        }


        private async Task PollingTick()
        {
            try
            {
                var processorConnectObj = new ProcessorConnectObj
                {
                    NextRunInterval = (int)_pollingInterval.TotalMilliseconds
                };
                await InternalConnect(processorConnectObj);
            }
            catch (Exception ex)
            {
                _logger.LogError($"Error in PollingTick: {ex.Message}", ex);
            }
        }

        private async Task HandleSystemUrlChangedAsync(SystemUrl newSystemUrl)
        {
            _systemUrl = newSystemUrl;
            await Reconnect();
        }
        public void Dispose()
        {
            _netConfig.OnSystemUrlChangedAsync -= HandleSystemUrlChangedAsync;
        }
        private static SystemUrl DeriveSystemUrl(NetConnectConfig netConnectConfig)
        {
            return netConnectConfig.LocalSystemUrl;
        }

        protected override void InitRabbitMQObjs()
        {
            _rabbitMQObjs = new List<RabbitMQObj>();
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorConnect" + _netConfig.AppID,
                FuncName = "processorConnect",
                MessageTimeout = 60000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "removePingInfos" + _netConfig.AppID,
                FuncName = "removePingInfos",
                MessageTimeout = 60000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorInit" + _netConfig.AppID,
                FuncName = "processorInit"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorAlertFlag" + _netConfig.AppID,
                FuncName = "processorAlertFlag"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorAlertSent" + _netConfig.AppID,
                FuncName = "processorAlertSent"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorQueueDic" + _netConfig.AppID,
                FuncName = "processorQueueDic"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorResetAlerts" + _netConfig.AppID,
                FuncName = "processorResetAlerts"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorWakeUp" + _netConfig.AppID,
                FuncName = "processorWakeUp",
                MessageTimeout = 60000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorAuthKey" + _netConfig.AppID,
                FuncName = "processorAuthKey",
                MessageTimeout = 600000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorUserEvent" + _netConfig.AppID,
                FuncName = "processorUserEvent",
                MessageTimeout = 600000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorScan" + _netConfig.AppID,
                FuncName = "processorScan",
                MessageTimeout = 6000000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorCommand" + _netConfig.AppID,
                FuncName = "processorCommand",
                MessageTimeout = 6000000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "addCmdProcessor" + _netConfig.AppID,
                FuncName = "addCmdProcessor",
                MessageTimeout = 60000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "getCommandHelp" + _netConfig.AppID,
                FuncName = "getCommandHelp",
                MessageTimeout = 60000
            });

        }
        protected override async Task<ResultObj> DeclareConsumers()
        {
            var result = new ResultObj();
            try
            {
                foreach (var rabbitMQObj in _rabbitMQObjs)

                {
                    rabbitMQObj.Consumer = new AsyncEventingBasicConsumer(rabbitMQObj.ConnectChannel);
                    if (rabbitMQObj.ConnectChannel != null)
                    {
                        switch (rabbitMQObj.FuncName)
                        {
                            case "processorConnect":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                                    {
                                        try
                                        {
                                            result = Connect(ConvertToObject<ProcessorConnectObj>(model, ea));
                                            await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                        }
                                        catch (Exception ex)
                                        {
                                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorConnect " + ex.Message);
                                        }
                                    };
                                break;
                            case "removePingInfos":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = RemovePingInfos(ConvertToObject<ProcessorDataObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.removePingInfos " + ex.Message);
                                }
                            };
                                break;
                            case "processorInit":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await Init(ConvertToObject<ProcessorInitObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorInit " + ex.Message);
                                }
                            };
                                break;
                            case "processorAlertFlag":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = AlertFlag(ConvertToList<List<int>>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorAlertFlag " + ex.Message);
                                }
                            };
                                break;
                            case "processorAlertSent":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = AlertSent(ConvertToList<List<int>>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorAlertSent " + ex.Message);
                                }
                            };
                                break;
                            case "processorQueueDic":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = QueueDic(ConvertToObject<ProcessorQueueDicObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorQueueDic " + ex.Message);
                                }
                            };
                                break;
                            case "processorResetAlerts":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await ResetAlerts(ConvertToList<List<int>>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorResetAlerts " + ex.Message);
                                }
                            };
                                break;
                            case "processorWakeUp":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await WakeUp();
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorWakeUp " + ex.Message);
                                }
                            };
                                break;
                            case "processorAuthKey":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await SetAuthKey(ConvertToObject<ProcessorInitObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorAuthKey " + ex.Message);
                                }
                            };
                                break;
                            case "processorUserEvent":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await ProcessorUserEvent(ConvertToObject<ProcessorUserEventObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorUserEvent " + ex.Message);
                                }
                            };
                                break;
                            case "processorScan":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await ProcessorScan(ConvertToObject<ProcessorScanDataObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorScan " + ex.Message);
                                }
                            };
                                break;
                            case "processorCommand":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    _ = ProcessorCommand(ConvertToObject<ProcessorScanDataObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorCommand " + ex.Message);
                                }
                            };
                                break;
                            case "getCommandHelp":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    _ = GetCommandHelp(ConvertToObject<ProcessorScanDataObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.getCommandHelp " + ex.Message);
                                }
                            };
                                break;

                            case "addCmdProcessor":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    _ = AddCmdProcessor(ConvertToObject<ProcessorScanDataObj>(model, ea));
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.addCmdProcessor " + ex.Message);
                                }
                            };
                                break;
                            case "getCommandList":
                                await rabbitMQObj.ConnectChannel.BasicQosAsync(prefetchSize: 0, prefetchCount: 1, global: false);
                                rabbitMQObj.Consumer.ReceivedAsync += async (model, ea) =>
                            {
                                try
                                {
                                    result = await GetCommandList();
                                    await rabbitMQObj.ConnectChannel.BasicAckAsync(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.getCommandList " + ex.Message);
                                }
                            };
                                break;
                        }
                    }
                }
                result.Success = true;
                result.Message += " Success : Declared all consumers ";
            }
            catch (Exception e)
            {
                string message = " Error : failed to declate consumers. Error was : " + e.ToString() + " . ";
                result.Message += message;
                Console.WriteLine(result.Message);
                result.Success = false;
            }
            return result;
        }
        public ResultObj Connect(ProcessorConnectObj? connectObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorConnect : ";
            if (connectObj == null)
            {
                result.Success = false;
                result.Message += "Error : connectObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                if (connectObj.NextRunInterval != 0 && connectObj.NextRunInterval != _pollingInterval.TotalMilliseconds)
                {
                    // Update the interval and restart the timer if necessary
                    _pollingInterval = TimeSpan.FromSeconds(connectObj.NextRunInterval);
                    _pollingTimer.Interval = _pollingInterval.TotalMilliseconds;
                    _pollingTimer.Stop();
                    _pollingTimer.Start();
                    result.Message += $" Success : Reset schedule interval to {connectObj.NextRunInterval}";
                }
                else
                {
                    // Check if the timer is running; if not, start it.
                    if (!_pollingTimer.Enabled)
                    {
                        _pollingTimer.Start();
                        result.Message += " Warning : Timer was not running and has been started.";
                    }
                    else
                    {
                        result.Message += " Success : Timer is already running. No change to schedule interval.";
                    }
                }

                result.Success = true;
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to run Connect : Error was : " + e.ToString() + " ";
            }
            if (result.Success == true)
                _logger.LogInformation(result.Message);
            else _logger.LogError(result.Message);
            return result;
        }

        private async Task<ResultObj> InternalConnect(ProcessorConnectObj? connectObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "RabbitListener : InternalConnect : ";
            if (connectObj == null)
            {
                result.Success = false;
                result.Message += "Error : connectObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                ResultObj connectResult = await _monitorPingProcessor.Connect(connectObj);
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                if (result.Success == true)
                    _logger.LogInformation(result.Message);
                else _logger.LogError(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to run Connect : Error was : " + e.ToString() + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public ResultObj RemovePingInfos(ProcessorDataObj? processorDataObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : RemovePingInfos : ";
            if (processorDataObj == null)
            {
                result.Success = false;
                result.Message += "Error : processorDataObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                _monitorPingProcessor.ProcessesMonitorReturnData(processorDataObj);
                result.Message += "Success : updated RemovePingInfos. ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += "Error : Failed to remove PingInfos: Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public async Task<ResultObj> ProcessorCommand(ProcessorScanDataObj? processorScanDataObj)
        {
            string? processorType = "";
            var result = new ResultObj();
            result.Success = false;



            if (processorScanDataObj == null)
            {
                result.Message += "Error : processorScanDataObj was null.";
                _logger.LogError(result.Message);
                return result;
            }

            if (processorScanDataObj.AuthKey != _netConfig.AuthKey)
            {
                result.Message += "Error : AuthKey not valid.";
                _logger.LogError(result.Message);
                return result;
            }
            processorType = processorScanDataObj.Type;
            if (string.IsNullOrEmpty(processorType))
            {
                result.Message += $"Error : cmd_processor_type was null or empty.";
                _logger.LogError(result.Message);
                return result;
            }
            var processor = _cmdProcessorProvider.GetProcessor(processorType);
            if (processor == null)
            {
                result.Message += $"Error : {processorType} cmd processor not available for this agent. Try calling get_cmd_list to get a list of cmd processors.";
                _logger.LogError(result.Message);
                processorScanDataObj.ScanCommandOutput = result.Message;
                PublishScanProcessorDataObj(processorScanDataObj)
                return result;
            }

            result.Message = $"MessageAPI : Processor{processorType}Command : ";


            try
            {
                TimeSpan timeout = TimeSpan.FromSeconds(processorScanDataObj.TimeoutSeconds);
                var cts = new CancellationTokenSource(timeout);
                _logger.LogInformation($"{result.Message} Queued {processorType} Command with arguments {processorScanDataObj.Arguments}");
                var commandResult = await processor.QueueCommand(cts, processorScanDataObj);
                result.Message += $"Success: Ran {processorType} command. Command Result: {commandResult.Message}";
                result.Success = commandResult.Success;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Message += $"Error : Failed to run {processorType} Command: Error was : {e.Message}";
                _logger.LogError(result.Message);
            }

            return result;
        }

        public async Task<ResultObj> GetCommandHelp(ProcessorScanDataObj? processorScanDataObj)
        {
            string? processorType = "";
            var result = new ResultObj();
            result.Success = false;



            if (processorScanDataObj == null)
            {
                result.Message += "Error : processorScanDataObj was null.";
                _logger.LogError(result.Message);
                return result;
            }

            if (processorScanDataObj.AuthKey != _netConfig.AuthKey)
            {
                result.Message += "Error : AuthKey not valid.";
                _logger.LogError(result.Message);
                return result;
            }
            processorType = processorScanDataObj.Type;
            if (string.IsNullOrEmpty(processorType))
            {
                result.Message += $"Error : cmd_processor_type was null or empty.";
                _logger.LogError(result.Message);
                processorScanDataObj.ScanCommandOutput = result.Message;
                PublishScanProcessorDataObj(processorScanDataObj)
                return result;
            }
            var processor = _cmdProcessorProvider.GetProcessor(processorType);
            if (processor == null)
            {
                result.Message += $"Error : {processorType} cmd processor not available for this agent. Try calling get_cmd_list to get a list of cmd processors.";
                processorScanDataObj.ScanCommandOutput = result.Message;
                PublishScanProcessorDataObj(processorScanDataObj)
                _logger.LogError(result.Message);
                return result;
            }

            result.Message = $"MessageAPI : {processorType} GetCommandHelp";


            try
            {
                var commandResult = await processor.PublishCommandHelp(processorScanDataObj);
                result.Message += $"Success: Ran get {processorType} help. Result: {commandResult.Message}";
                result.Success = commandResult.Success;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Message += $"Error : Failed to run get {processorType} help : Error was : {e.Message}";
                _logger.LogError(result.Message);
            }

            return result;
        }

        public async Task<ResultObj> GetCommandList(ProcessorScanDataObj? processorScanDataObj)
        {
            string? processorType = "";
            var result = new ResultObj();
            result.Success = false;



            if (processorScanDataObj == null)
            {
                result.Message += "Error : processorScanDataObj was null.";
                _logger.LogError(result.Message);
                return result;
            }

            if (processorScanDataObj.AuthKey != _netConfig.AuthKey)
            {
                result.Message += "Error : AuthKey not valid.";
                _logger.LogError(result.Message);
                return result;
            }



            result.Message = $"MessageAPI : {processorType} GetCommandList";


            try
            {
                var processorTypes = _cmdProcessorProvider.ProcessorTypes;
                var processorTypesString = string.Join(", ", processorTypes.Select(type => $"'{type}'"));
                string message = $"Success: got the list of cmd processor types for the agent. cmd_processor_types : [{processorTypesString}]";
                processorScanDataObj.ScanCommandOutput = message;
                var resultPublish = PublishScanProcessorDataObj(processorScanDataObj);
                result.Success = resultPublish.Success;
                result.Message += resultPublish.Message;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Message += $"Error : Failed to run get cmd processor list : Error was : {e.Message}";
                _logger.LogError(result.Message);
            }

            return result;
        }


        public async Task<ResultObj> ProcessorScan(ProcessorScanDataObj? processorScanDataObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorScan : ";
            if (processorScanDataObj == null)
            {
                result.Success = false;
                result.Message += "Error : processorScanDataObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            if (processorScanDataObj.AuthKey != _netConfig.AuthKey)
            {
                result.Success = false;
                result.Message += "Error : AuthKey not valid .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                _cmdProcessorProvider.GetProcessor("nmap").UseDefaultEndpoint = processorScanDataObj.UseDefaultEndpoint;
                await _cmdProcessorProvider.GetProcessor("nmap").Scan();
                result.Message += "Success : updated RemovePingInfos. ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += "Error : Failed to remove PingInfos: Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public async Task<ResultObj> Init(ProcessorInitObj? initObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = " MessageAPI : Start ProcessorInit : ";
            if (initObj == null)
            {
                result.Success = false;
                result.Message += " Error : initObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            if (initObj.AuthKey != _netConfig.AuthKey)
            {
                result.Success = false;
                result.Message += "Error : AuthKey not valid .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                await _monitorPingProcessor.Init(initObj);
                result.Message += " Finished Processor.Init . ";
                result.Success = true;
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public ResultObj AlertFlag(List<int>? monitorPingInfoIds)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertFlag : ";
            if (monitorPingInfoIds == null)
            {
                result.Success = false;
                result.Message += "Error : monitorPingInfoIds was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                monitorPingInfoIds.ForEach(f => _logger.LogDebug("ProcessorAlertFlag Found MonitorPingInfo ID=" + f));
                List<ResultObj> results = _monitorPingProcessor.UpdateAlertFlag(monitorPingInfoIds, true);
                result.Success = results.Where(w => w.Success == false).ToList().Count() == 0;
                if (result.Success) result.Message += "Success ran ok ";
                else
                {
                    results.Select(s => s.Message).ToList().ForEach(f => result.Message += f);
                    result.Data = results;
                }
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public ResultObj AlertSent(List<int>? monitorIPIDs)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertSent : ";
            if (monitorIPIDs == null)
            {
                result.Success = false;
                result.Message += "Error : monitorIPIDs was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                monitorIPIDs.ForEach(f => _logger.LogDebug("ProcessorSentFlag Found monitorIPID =" + f));
                List<ResultObj> results = _monitorPingProcessor.UpdateAlertSent(monitorIPIDs, true);
                result.Success = results.Where(w => w.Success == false).ToList().Count() == 0;
                if (result.Success) result.Message += "Success ran ok ";
                else
                {
                    results.Select(s => s.Message).ToList().ForEach(f => result.Message += f);
                    result.Data = results;
                }
                _logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public async Task<ResultObj> ResetAlerts(List<int>? monitorIPIDs)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorResetAlerts : ";
            if (monitorIPIDs == null)
            {
                result.Success = false;
                result.Message += "Error : monitorIPIDs was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                var results = await _monitorPingProcessor.ResetAlerts(monitorIPIDs);
                results.ForEach(f => result.Message += f.Message);
                result.Success = results.All(a => a.Success == true) && results.Count() != 0;
                result.Data = results;
                if (result.Success == true)
                    _logger.LogInformation(result.Message);
                else _logger.LogError(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public ResultObj QueueDic(ProcessorQueueDicObj? queueDicObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorQueueDic : ";
            if (queueDicObj == null)
            {
                result.Success = false;
                result.Message += "Error : queueDicObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            if (queueDicObj.AuthKey != _netConfig.AuthKey)
            {
                result.Success = false;
                result.Message += "Error : AuthKey not valid .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                ResultObj connectResult = _monitorPingProcessor.AddMonitorIPsToQueueDic(queueDicObj);
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                if (connectResult.Success)
                {
                    var processorUserEventObj = new ProcessorUserEventObj();
                    processorUserEventObj.IsHostsAdded = true;
                    _monitorPingProcessor.ProcessorUserEvent(processorUserEventObj);
                }
                if (result.Success == true)
                    _logger.LogInformation(result.Message);
                else _logger.LogError(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }

        public async Task<ResultObj> SetAuthKey(ProcessorInitObj? processorInitObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : SetAuthKey : ";
            if (processorInitObj == null)
            {
                result.Success = false;
                result.Message += " Error : processorInitObj was null .";
                _logger.LogError(result.Message);
                return result;

            }
            if (processorInitObj.AuthKey == null)
            {
                result.Success = false;
                result.Message += " Error : authKey was null .";
                _logger.LogError(result.Message);
                return result;

            }
            try
            {
                ResultObj connectResult = await _monitorPingProcessor.SetAuthKey(processorInitObj);
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                if (result.Success == true)
                    _logger.LogInformation(result.Message);
                else _logger.LogError(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += " Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        public async Task<ResultObj> ProcessorUserEvent(ProcessorUserEventObj? processorUserEventObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorUserEvent : ";
            if (processorUserEventObj == null)
            {
                result.Success = false;
                result.Message += " Error : processorUserEventObj was null .";
                _logger.LogError(result.Message);
                return result;

            }

            try
            {
                ResultObj connectResult = await _monitorPingProcessor.ProcessorUserEvent(processorUserEventObj);
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                if (result.Success == true)
                    _logger.LogInformation(result.Message);
                else _logger.LogError(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += " Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }

        public async Task<ResultObj> WakeUp()
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = " MessageAPI : WakeUp : ";
            try
            {
                ResultObj connectResult = await _monitorPingProcessor.WakeUp();
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                if (result.Success == true)
                    _logger.LogInformation(result.Message);
                else _logger.LogError(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += " Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.LogError(result.Message);
            }
            return result;
        }
        private async Task<ResultObj> AddCmdProcessor(ProcessorScanDataObj? processorScanDataObj)
        {
            var result = new ResultObj { Success = false };

            try
            {
                if (processorScanDataObj == null)
                {
                    result.Success = false;
                    result.Message += "Error : processorScanDataObj was null .";
                    _logger.LogError(result.Message);
                    return result;

                }
                if (processorScanDataObj.AuthKey != _netConfig.AuthKey)
                {
                    result.Success = false;
                    result.Message += "Error : AuthKey not valid .";
                    _logger.LogError(result.Message);
                    return result;

                }
                result = await _cmdProcessorProvider.AddCmdProcessor(processorScanDataObj);

            }
            catch (Exception ex)
            {
                result.Success = false;
                result.Message = $"Error adding CmdProcessor: {ex.Message}";
                _logger.LogError(result.Message);
            }

            return result;
        }

    }
}