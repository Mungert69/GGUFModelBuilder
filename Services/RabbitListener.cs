using RabbitMQ.Client;
using RabbitMQ.Client.Events;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Connection;
using NetworkMonitor.Processor.Services;
using System.Collections.Generic;
using System;
using System.Threading.Tasks;
using System.Linq;
using NetworkMonitor.Utils;
using NetworkMonitor.Utils.Helpers;
using Microsoft.Extensions.Logging;
namespace NetworkMonitor.Objects.Repository
{
    public interface IRabbitListener
    {
        Task<ResultObj> Connect(ProcessorConnectObj connectObj);
        ResultObj RemovePingInfos(ProcessorDataObj processorDataObj);
        Task<ResultObj> Init(ProcessorInitObj initObj);
        ResultObj AlertFlag(List<int> monitorPingInfoIds);
        ResultObj AlertSent(List<int> monitorIPIDs);
        ResultObj ResetAlerts(List<int> monitorIPIDs);
        ResultObj QueueDic(ProcessorQueueDicObj queueDicObj);
        ResultObj WakeUp();
    }
    public class RabbitListener : RabbitListenerBase, IRabbitListener
    {
        //private string _appID;
        private IMonitorPingProcessor _monitorPingProcessor;
        NetConnectConfig _netConfig;

       
        public RabbitListener(IMonitorPingProcessor monitorPingProcessor, ILogger logger, NetConnectConfig netConnectConfig) : base(logger, DeriveSystemUrl(netConnectConfig))
        {
            _monitorPingProcessor = monitorPingProcessor;
            //_appID = monitorPingProcessor.AppID;
            _netConfig = netConnectConfig;
            _netConfig.OnSystemUrlChanged += HandleSystemUrlChanged;

            Setup();
        }

        private void HandleSystemUrlChanged(SystemUrl newSystemUrl)
        {
            _systemUrl = newSystemUrl;
            Reconnect();
        }
        public void Dispose()
        {
            _netConfig.OnSystemUrlChanged -= HandleSystemUrlChanged;
        }
        private static SystemUrl DeriveSystemUrl(NetConnectConfig netConnectConfig)
        {
            return netConnectConfig.LocalSystemUrl;
        }
        protected override void InitRabbitMQObjs()
        {
            _rabbitMQObjs=new List<RabbitMQObj>();
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorConnect" + _netConfig.AppID,
                FuncName = "processorConnect",
                MessageTimeout = 60000
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "removePingInfos" + _netConfig.AppID,
                FuncName = "removePingInfos"
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
        }
        protected override ResultObj DeclareConsumers()
        {
            var result = new ResultObj();
            try
            {
                _rabbitMQObjs.ForEach(rabbitMQObj =>
            {
                rabbitMQObj.Consumer = new EventingBasicConsumer(rabbitMQObj.ConnectChannel);
                switch (rabbitMQObj.FuncName)
                {
                    case "processorConnect":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += async (model, ea) =>
                            {
                                try
                                {
                                    result = await Connect(ConvertToObject<ProcessorConnectObj>(model, ea));
                                    rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                                }
                                catch (Exception ex)
                                {
                                    _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorConnect " + ex.Message);
                                }
                            };
                        break;
                    case "removePingInfos":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        try
                        {
                            result = RemovePingInfos(ConvertToObject<ProcessorDataObj>(model, ea));
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.removePingInfos " + ex.Message);
                        }
                    };
                        break;
                    case "processorInit":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += async (model, ea) =>
                    {
                        try
                        {
                            result = await Init(ConvertToObject<ProcessorInitObj>(model, ea));
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorInit " + ex.Message);
                        }
                    };
                        break;
                    case "processorAlertFlag":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        try
                        {
                            result = AlertFlag(ConvertToList<List<int>>(model, ea));
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorAlertFlag " + ex.Message);
                        }
                    };
                        break;
                    case "processorAlertSent":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        try
                        {
                            result = AlertSent(ConvertToList<List<int>>(model, ea));
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorAlertSent " + ex.Message);
                        }
                    };
                        break;
                    case "processorQueueDic":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        try
                        {
                            result = QueueDic(ConvertToObject<ProcessorQueueDicObj>(model, ea));
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorQueueDic " + ex.Message);
                        }
                    };
                        break;
                    case "processorResetAlerts":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        try
                        {
                            result = ResetAlerts(ConvertToList<List<int>>(model, ea));
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorResetAlerts " + ex.Message);
                        }
                    };
                        break;
                    case "processorWakeUp":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        try
                        {
                            result = WakeUp();
                            rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogError(" Error : RabbitListener.DeclareConsumers.processorWakeUp " + ex.Message);
                        }
                    };
                        break;
                }
            });
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
        public async Task<ResultObj> Connect(ProcessorConnectObj connectObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorConnect : ";
            try
            {
                ResultObj connectResult = await _monitorPingProcessor.Connect(connectObj);
                result.Message += connectResult.Message;
                result.Success = connectResult.Success;
                result.Data = connectResult.Data;
                _logger.LogInformation(result.Message);
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
        public ResultObj RemovePingInfos(ProcessorDataObj processorDataObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : RemovePingInfos : ";
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
        public async Task<ResultObj> Init(ProcessorInitObj initObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorInit : ";
            try
            {
                await _monitorPingProcessor.Init(initObj);
                result.Message += "Success ran ok ";
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
        public ResultObj AlertFlag(List<int> monitorPingInfoIds)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertFlag : ";
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
        public ResultObj AlertSent(List<int> monitorIPIDs)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorAlertSent : ";
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
        public ResultObj ResetAlerts(List<int> monitorIPIDs)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorResetAlerts : ";
            try
            {
                var results = _monitorPingProcessor.ResetAlerts(monitorIPIDs);
                results.ForEach(f => result.Message += f.Message);
                result.Success = results.All(a => a.Success == true) && results.Count() != 0;
                result.Data = results;
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
        public ResultObj QueueDic(ProcessorQueueDicObj queueDicObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorQueueDic : ";
            try
            {
                _monitorPingProcessor.AddMonitorIPsToQueueDic(queueDicObj);
                result.Message += "Success ran ok ";
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
        public ResultObj WakeUp()
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : WakeUp : ";
            try
            {
                result = _monitorPingProcessor.WakeUp();
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
    }
}