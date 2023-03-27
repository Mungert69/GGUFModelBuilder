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
using MetroLog;
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
        private IConnection _connection;
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
                UserName = "usercommonxf1",
                Password = "test12",
                VirtualHost = "/vhostuser",
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
                FuncName = "processorConnect",
                MessageTimeout=60000
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
                FuncName = "processorWakeUp",
                MessageTimeout=60000
            });
            _connection = _factory.CreateConnection();
            _publishChannel = _connection.CreateModel();
            _rabbitMQObjs.ForEach(r => r.ConnectChannel = _connection.CreateModel());
            var results=new List<ResultObj>();
            results.Add(DeclareQueues());
            results.Add(DeclareConsumers());
            results.Add(BindChannelToConsumer());
            bool flag=true;
            string messages="";
            results.ForEach(f => messages+=f.Message);
            results.ForEach(f => flag=f.Success && flag);
            if (flag) _logger.Info("Success : Setup RabbitListener messages were : "+messages);
            else _logger.Fatal("Error : Failed to setup RabbitListener messages were : "+messages);

        }
        private ResultObj DeclareQueues()
        {
            var result = new ResultObj();
            result.Message = " RabbitRepo DeclareQueues : ";
            try
            {
                _rabbitMQObjs.ForEach(rabbitMQObj =>
                    {
                        var args = new Dictionary<string, object>();
                        if (rabbitMQObj.MessageTimeout!=0){
                            args.Add("x-message-ttl", rabbitMQObj.MessageTimeout);
                        }
                        rabbitMQObj.QueueName = _instanceName + "-" + rabbitMQObj.ExchangeName;
                        rabbitMQObj.ConnectChannel.ExchangeDeclare(exchange: rabbitMQObj.ExchangeName, type: ExchangeType.Fanout, durable: true);
                        rabbitMQObj.ConnectChannel.QueueDeclare(queue: rabbitMQObj.QueueName,
                                             durable: true,
                                             exclusive: false,
                                             autoDelete: true,
                                             arguments: args);
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
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);
                        rabbitMQObj.Consumer.Received += (model, ea) =>
                            {
                                result = Connect(ConvertToObject<ProcessorConnectObj>(model, ea));
                                rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                            };
                        break;
                    case "removePingInfos":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = RemovePingInfos(ConvertToObject<ProcessorDataObj>(model, ea));
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                    };
                        break;
                    case "processorInit":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = Init(ConvertToObject<ProcessorInitObj>(model, ea));
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                    };
                        break;
                    case "processorAlertFlag":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = AlertFlag(ConvertToList<List<int>>(model, ea));
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                    };
                        break;
                    case "processorAlertSent":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = AlertSent(ConvertToList<List<int>>(model, ea));
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                    };
                        break;
                    case "processorQueueDic":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = QueueDic(ConvertToObject<ProcessorQueueDicObj>(model, ea));
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                    };
                        break;
                    case "processorResetAlerts":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = ResetAlerts(ConvertToList<List<int>>(model, ea));
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
                    };
                        break;
                    case "processorWakeUp":
                        rabbitMQObj.ConnectChannel.BasicQos(prefetchSize: 0, prefetchCount: 1, global: false);

                        rabbitMQObj.Consumer.Received += (model, ea) =>
                    {
                        result = WakeUp();
                        rabbitMQObj.ConnectChannel.BasicAck(ea.DeliveryTag, false);
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
                            consumer: rabbitMQObj.Consumer

                            );
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
            T result = null;
            try
            {
                string json = Encoding.UTF8.GetString(@event.Body.ToArray(), 0, @event.Body.ToArray().Length);
                var cloudEvent = JsonConvert.DeserializeObject<CloudEvent>(json);
                JObject dataAsJObject = (JObject)cloudEvent.Data;
                result = dataAsJObject.ToObject<T>();
            }
            catch (Exception e)
            {
                _logger.Error("Error : Unable to convert Object. Error was : " + e.ToString());

            }

            return result;
        }

 private T ConvertToList<T>(object sender, BasicDeliverEventArgs @event) where T : class
        {
            T result = null;
            try
            {
                string json = Encoding.UTF8.GetString(@event.Body.ToArray(), 0, @event.Body.ToArray().Length);
                var cloudEvent = JsonConvert.DeserializeObject<CloudEvent>(json);
                JArray dataAsJObject = (JArray)cloudEvent.Data;
                result = dataAsJObject.ToObject<T>();
            }
            catch (Exception e)
            {
                _logger.Error("Error : Unable to convert Object. Error was : " + e.ToString());

            }

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
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to run Connect : Error was : " + e.ToString() + " ";
                _logger.Error(result.Message);
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
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += "Error : Failed to remove PingInfos: Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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
                monitorPingInfoIds.ForEach(f => _logger.Debug("ProcessorAlertFlag Found MonitorPingInfo ID=" + f));
                List<ResultObj> results = _monitorPingProcessor.UpdateAlertFlag(monitorPingInfoIds, true);
                result.Success = results.Where(w => w.Success == false).ToList().Count() == 0;
                if (result.Success) result.Message += "Success ran ok ";
                else
                {
                    results.Select(s => s.Message).ToList().ForEach(f => result.Message += f);
                    result.Data = results;
                }
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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
                monitorIPIDs.ForEach(f => _logger.Debug("ProcessorSentFlag Found monitorIPID =" + f));
                List<ResultObj> results = _monitorPingProcessor.UpdateAlertSent(monitorIPIDs, true);
                result.Success = results.Where(w => w.Success == false).ToList().Count() == 0;
                if (result.Success) result.Message += "Success ran ok ";
                else
                {
                    results.Select(s => s.Message).ToList().ForEach(f => result.Message += f);
                    result.Data = results;
                }
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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
                result=_monitorPingProcessor.WakeUp();
                _logger.Info(result.Message);
            }
            catch (Exception e)
            {
                result.Data = null;
                result.Success = false;
                result.Message += "Error : Failed to receive message : Error was : " + e.Message + " ";
                _logger.Error(result.Message);
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