using RabbitMQ.Client;
using RabbitMQ.Client.Events;
using CloudNative.CloudEvents;
using CloudNative.CloudEvents.NewtonsoftJson;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Objects;
using NetworkMonitor.Processor.Services;
using System.Collections.Generic;
using System;
using System.Text;
using System.Linq;
using NetworkMonitor.Utils;
using Microsoft.Extensions.Logging;
namespace NetworkMonitor.Objects.Repository
{
    public class RabbitListener
    {
        private string _appID;
        private string _instanceName;
        private IModel _publishChannel;
        private ILogger _logger;
        private IMonitorPingProcessor _monitorPingProcessor;
        private ConnectionFactory _factory;
        List<RabbitMQObj> _rabbitMQObjs = new List<RabbitMQObj>();
        public RabbitListener(ILogger logger, IMonitorPingProcessor monitorPingProcessor, string appID, string instanceName, string hostname)
        {
            _logger = logger;
            _monitorPingProcessor = monitorPingProcessor;
            _appID = appID;
            _instanceName = instanceName;
            _factory = new ConnectionFactory
            {
                HostName = hostname,
                UserName = "guest",
                Password = "guest",
                AutomaticRecoveryEnabled = true,
                Port = 5672
            };
            init();
        }
        public void init()
        {
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorConnect" + _appID,
                FuncName = "processorConnect"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "removePingInfos" + _appID,
                FuncName = "removePingInfos"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorInit" + _appID,
                FuncName = "processorInit"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorAlertFlag" + _appID,
                FuncName = "processorAlertFlag"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorAlertSent" + _appID,
                FuncName = "processorAlertSent"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorQueueDic" + _appID,
                FuncName = "processorQueueDic"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorResetAlerts" + _appID,
                FuncName = "processorResetAlerts"
            });
            _rabbitMQObjs.Add(new RabbitMQObj()
            {
                ExchangeName = "processorWakeUp" + _appID,
                FuncName = "processorWakeUp"
            });
            var connection = _factory.CreateConnection();
            _publishChannel = connection.CreateModel();
            _rabbitMQObjs.ForEach(r => r.ConnectChannel = connection.CreateModel());
            Console.WriteLine(DeclareQueues().Message);
            Console.WriteLine(DeclareConsumers().Message);
            Console.WriteLine(BindChannelToConsumer().Message);
        }
        private ResultObj DeclareQueues()
        {
            var result = new ResultObj();
            result.Message = " RabbitRepo DeclareQueues : ";
            try
            {
                _rabbitMQObjs.ForEach(rabbitMQObj =>
                    {
                        rabbitMQObj.QueueName = _instanceName + "-" + rabbitMQObj.ExchangeName;
                        rabbitMQObj.ConnectChannel.ExchangeDeclare(exchange: rabbitMQObj.ExchangeName, type: ExchangeType.Fanout, durable: true);
                        rabbitMQObj.ConnectChannel.QueueDeclare(queue: rabbitMQObj.QueueName,
                                             durable: true,
                                             exclusive: false,
                                             autoDelete: true,
                                             arguments: null);
                        rabbitMQObj.ConnectChannel.QueueBind(queue: rabbitMQObj.QueueName,
                                          exchange: rabbitMQObj.ExchangeName,
                                          routingKey: string.Empty);
                    });
                result.Success = true;
                result.Message += " Success : Declared all queues ";
            }
            catch (Exception e)
            {
                string message = " Error : failed to declate queues. Error was : " + e.ToString() + " . ";
                result.Message += message;
                Console.WriteLine(result.Message);
                result.Success = false;
            }
            return result;
        }
        private ResultObj DeclareConsumers()
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
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                            {
                                result = Connect(ConvertToObject<ProcessorConnectObj>(model, ea));
                            };
                        break;
                    case "removePingInfos":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = RemovePingInfos(ConvertToObject<ProcessorDataObj>(model, ea));
                    };
                        break;
                    case "processorInit":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = Init(ConvertToObject<ProcessorInitObj>(model, ea));
                    };
                        break;
                    case "processorAlertFlag":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = AlertFlag(ConvertToObject<List<int>>(model, ea));
                    };
                        break;
                    case "processorAlertSent":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = AlertSent(ConvertToObject<List<int>>(model, ea));
                    };
                        break;
                    case "processorQueueDic":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = QueueDic(ConvertToObject<ProcessorQueueDicObj>(model, ea));
                    };
                        break;
                    case "processorResetAlerts":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = ResetAlerts(ConvertToObject<List<int>>(model, ea));
                    };
                        break;
                    case "processorWakeUp":
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = WakeUp();
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
        private ResultObj BindChannelToConsumer()
        {
            var result = new ResultObj();
            result.Message = " RabbitRepo BindChannelToConsumer : ";
            try
            {
                _rabbitMQObjs.ForEach(rabbitMQObj =>
                    {
                        rabbitMQObj.ConnectChannel.BasicConsume(queue: rabbitMQObj.QueueName,
                            autoAck: false,
                            consumer: rabbitMQObj.Consumer);
                    });
                result.Success = true;
                result.Message += " Success :  bound all consumers to queues ";
            }
            catch (Exception e)
            {
                string message = " Error : failed to bind all consumers to queues. Error was : " + e.ToString() + " . ";
                result.Message += message;
                Console.WriteLine(result.Message);
                result.Success = false;
            }
            return result;
        }
        private T ConvertToObject<T>(object sender, BasicDeliverEventArgs @event) where T : class
        {
            string json = Encoding.UTF8.GetString(@event.Body.ToArray(), 0, @event.Body.ToArray().Length);
            var cloudEvent = JsonConvert.DeserializeObject<CloudEvent>(json);
            JObject dataAsJObject = (JObject)cloudEvent.Data;
            var result = dataAsJObject.ToObject<T>();
            return result;
        }
        public ResultObj Connect(ProcessorConnectObj connectObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorConnect : ";
            try
            {
                ResultObj connectResult = _monitorPingProcessor.Connect(connectObj);
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
        public ResultObj Init(ProcessorInitObj initObj)
        {
            ResultObj result = new ResultObj();
            result.Success = false;
            result.Message = "MessageAPI : ProcessorInit : ";
            try
            {
                _monitorPingProcessor.init(initObj);
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
                _monitorPingProcessor.Awake = true;
                result.Message += "Success ran WakeUp ok ";
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
        public string PublishJsonZ<T>(string exchangeName, T obj) where T : class
        {
            var datajson = JsonUtils.writeJsonObjectToString<T>(obj);
            string datajsonZ = StringCompressor.Compress(datajson);
            CloudEvent cloudEvent = new CloudEvent
            {
                Id = "event-id",
                Type = "event-type",
                Source = new Uri("https://srv1.mahadeva.co.uk"),
                Time = DateTimeOffset.UtcNow,
                Data = datajsonZ
            };
            var formatter = new JsonEventFormatter();
            var json = formatter.ConvertToJObject(cloudEvent);
            string message = json.ToString();
            var body = Encoding.UTF8.GetBytes(message);
            _publishChannel.BasicPublish(exchange: exchangeName,
                                 routingKey: string.Empty,
                                 basicProperties: null,
                                 // body: formatter.EncodeBinaryModeEventData(cloudEvent));
                                 body: body);
            return datajsonZ;
        }
        public void Publish<T>(string exchangeName, T obj) where T : class
        {
            CloudEvent cloudEvent = new CloudEvent
            {
                Id = "event-id",
                Type = "event-type",
                Source = new Uri("https://srv1.mahadeva.co.uk"),
                Time = DateTimeOffset.UtcNow,
                Data = obj
            };
            var formatter = new JsonEventFormatter();
            var json = formatter.ConvertToJObject(cloudEvent);
            string message = json.ToString();
            var body = Encoding.UTF8.GetBytes(message);
            _publishChannel.BasicPublish(exchange: exchangeName,
                                 routingKey: string.Empty,
                                 basicProperties: null,
                                 // body: formatter.EncodeBinaryModeEventData(cloudEvent));
                                 body: body);
        }
        public void Publish(string exchangeName, Object obj)
        {
            CloudEvent cloudEvent = new CloudEvent
            {
                Id = "event-id",
                Type = "event-type",
                Source = new Uri("https://srv1.mahadeva.co.uk"),
                Time = DateTimeOffset.UtcNow,
                Data = obj
            };
            var formatter = new JsonEventFormatter();
            var json = formatter.ConvertToJObject(cloudEvent);
            string message = json.ToString();
            var body = Encoding.UTF8.GetBytes(message);
            _publishChannel.BasicPublish(exchange: exchangeName,
                                 routingKey: string.Empty,
                                 basicProperties: null,
                                 // body: formatter.EncodeBinaryModeEventData(cloudEvent));
                                 body: body);
        }
    }
}