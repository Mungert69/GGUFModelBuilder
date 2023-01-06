using System;
using System.Collections.Generic;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Dapr;
using NetworkMonitor.Utils;
using NetworkMonitor.Utils.Helpers;
using NetworkMonitor.Objects.ServiceMessage;
using System.Linq;
using NetworkMonitor.Connection;
using System.Threading.Tasks;
using System.Threading;
using System.Diagnostics;
using Dapr.Client;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Configuration;

namespace NetworkMonitor.Processor.Services
{

    public class MonitorPingProcessor : IMonitorPingProcessor
    {
        private PingParams _pingParams;

        private Dictionary<string, string> _daprMetadata = new Dictionary<string, string>();
        private bool _awake;
        private ILogger _logger;
        private List<NetConnect> _netConnects = null;
        private Dictionary<string, List<MonitorIP>> _monitorIPQueueDic = new Dictionary<string, List<MonitorIP>>();
        private List<MonitorIP> _monitorIPQueue = new List<MonitorIP>();
        private DaprClient _daprClient;
        private string _appID = "1";

        private IConnectFactory _connectFactory;
        private List<MonitorPingInfo> _monitorPingInfos = new List<MonitorPingInfo>();

        public bool Awake { get => _awake; set => _awake = value; }

        public MonitorPingProcessor(IConfiguration config, ILogger<MonitorPingProcessor> logger, DaprClient daprClient, IHostApplicationLifetime appLifetime, IConnectFactory connectFactory)
        {
            appLifetime.ApplicationStopping.Register(OnStopping);
            _logger = logger;
            _daprClient = daprClient;
            _daprMetadata.Add("ttlInSeconds", "60");

            _appID = config.GetValue<string>("AppID");
            _connectFactory = connectFactory;
            init(new ProcessorInitObj());
        }

        private void OnStopping()
        {
            Console.WriteLine("PROCESSOR SHUTDOWN : starting shutdown of MonitorPingService");
            try
            {
                PublishMonitorPingInfos(true);
                _logger.LogDebug("MonitorPingInfos StateStore : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));

                ProcessorInitObj processorObj = new ProcessorInitObj();
                processorObj.IsProcessorReady = false;
                processorObj.AppID = _appID;
                //_daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "processorReady", processorObj, _daprMetadata);
                DaprRepo.PublishEvent<ProcessorInitObj>(_daprClient, "processorReady", processorObj);
                _logger.LogInformation("Published event ProcessorItitObj.IsProcessorReady = false");

                _logger.LogWarning("PROCESSOR SHUTDOWN : Complete");
            }
            catch (Exception e)
            {
                _logger.LogCritical("Error : Failed to run SaveState before shutdown : Error Was : " + e.ToString() + " Inner Exception : " + e.InnerException.Message);
                Console.WriteLine();
            }
        }

        public void init(ProcessorInitObj initObj)
        {
            List<MonitorPingInfo> currentMonitorPingInfos;
            List<MonitorIP> stateMonitorIPs = new List<MonitorIP>();
            PingParams statePingParams = new PingParams();
            try
            {

                bool isDaprReady = _daprClient.CheckHealthAsync().Result;
                if (isDaprReady)
                {
                    if (initObj.TotalReset)
                    {
                        _logger.LogInformation("Resetting Processor MonitorPingInfos in statestore");
                        Dictionary<string, string> metadata = new Dictionary<string, string>();
                        var processorDataObj = new ProcessorDataObj()
                        {
                            MonitorPingInfos = new List<MonitorPingInfo>(),
                            PingInfos = new List<PingInfo>()
                        };
                        DaprRepo.SaveState(_daprClient, "ProcessorDataObj", processorDataObj);
                        //_daprClient.SaveStateAsync<List<MonitorPingInfo>>("statestore", "MonitorPingInfos", new List<MonitorPingInfo>());
                        //_daprClient.SaveStateAsync<List<MonitorIP>>("statestore", "MonitorIPs", new List<MonitorIP>());
                        DaprRepo.SaveState<List<MonitorIP>>(_daprClient, "MonitorIPs", new List<MonitorIP>());
                        //_daprClient.SaveStateAsync<PingParams>("statestore", "PingParams", new PingParams());
                        DaprRepo.SaveState<PingParams>(_daprClient, "PingParams", new PingParams());

                        currentMonitorPingInfos = new List<MonitorPingInfo>();
                        _logger.LogInformation("Reset MonitorPingInfos in statestore ");
                    }
                    else
                    {
                        if (initObj.Reset)
                        {
                            _logger.LogInformation("Zeroing MonitorPingInfos for new DataSet");
                            foreach (MonitorPingInfo monitorPingInfo in _monitorPingInfos)
                            {
                                monitorPingInfo.DateStarted = DateTime.UtcNow;
                                monitorPingInfo.PacketsLost = 0;
                                monitorPingInfo.PacketsLostPercentage = 0;
                                monitorPingInfo.PacketsRecieved = 0;
                                monitorPingInfo.PacketsSent = 0;
                                monitorPingInfo.PingInfos = new List<PingInfo>();
                                monitorPingInfo.RoundTripTimeAverage = 0;
                                monitorPingInfo.RoundTripTimeMaximum = 0;
                                monitorPingInfo.RoundTripTimeMinimum = _pingParams.Timeout;
                                monitorPingInfo.RoundTripTimeTotal = 0;
                                monitorPingInfo.TimeOuts = 0;
                            }
                            currentMonitorPingInfos = _monitorPingInfos;
                        }
                        else
                        {

                            //statePingParams = _daprClient.GetStateAsync<PingParams>("statestore", "PingParams").Result;
                            statePingParams = DaprRepo.GetState<PingParams>(_daprClient, "PingParams");
                            _logger.LogInformation("PingParams from statestore ");

                            //stateMonitorIPs = _daprClient.GetStateAsync<List<MonitorIP>>("statestore", "MonitorIPs").Result;
                            stateMonitorIPs = DaprRepo.GetState<List<MonitorIP>>(_daprClient, "MonitorIPs");
                            if (stateMonitorIPs != null) _logger.LogInformation("MonitorIPS from statestore count =" + stateMonitorIPs.Count());

                            try
                            {
                                // Trying both ways until upgrade complete.

                                currentMonitorPingInfos = ProcessorDataBuilder.Build(DaprRepo.GetState<ProcessorDataObj>(_daprClient, "ProcessorDataObj"));

                                _logger.LogInformation("Success : Building MonitorPingInfos from ProcessorDataObj in statestore");

                            }
                            catch (Exception)
                            {
                                _logger.LogError("Error : Building MonitorPingInfos from ProcessorDataObj in statestore");
                                currentMonitorPingInfos = _daprClient.GetStateAsync<List<MonitorPingInfo>>("statestore", "MonitorPingInfos").Result;
                                _logger.LogInformation("Success : Retry reading MonitorPingInfos as Object from statestore");

                            }
                            //Publish to MonitorService if redis contains data
                            if (currentMonitorPingInfos.Count > 0)
                            {
                                PublishMonitorPingInfos(false);
                            }
                        }
                    }

                }
                else
                {
                    _logger.LogError("Dapr Client Status is not healthy");
                    currentMonitorPingInfos = new List<MonitorPingInfo>();
                }

            }
            catch (Exception e)
            {
                _logger.LogError("Failed : Loading statestore : Error was : " + e.ToString());
                currentMonitorPingInfos = new List<MonitorPingInfo>();
            }

            try
            {
                if (initObj.MonitorIPs == null || initObj.MonitorIPs.Count == 0)
                {
                    _logger.LogWarning("Warning : There are No MonitorIPs using statestore");
                    initObj.MonitorIPs = stateMonitorIPs;
                    if (stateMonitorIPs.Count == 0)
                    {
                        _logger.LogError("Error : There are No MonitorIPs in statestore");
                    }
                }
                else
                {
                    //_daprClient.SaveStateAsync<List<MonitorIP>>("statestore", "MonitorIPs", initObj.MonitorIPs);
                    DaprRepo.SaveState<List<MonitorIP>>(_daprClient, "MonitorIPs", initObj.MonitorIPs);
                }
                if (initObj.PingParams == null)
                {
                    _logger.LogWarning("Warning : There are No PingParams using statestore");
                    _pingParams = statePingParams;
                    if (statePingParams == null)
                    {
                        _logger.LogError("Error : There are No PingParams in statestore");
                    }
                }
                else
                {
                    _daprClient.SaveStateAsync<PingParams>("statestore", "PingParams", initObj.PingParams);
                    _pingParams = initObj.PingParams;
                }

                if (SystemParamsHelper.IsSystemElevatedPrivilege)
                {
                    _logger.LogInformation("Ping Payload can be customised.  Program is running under privileged user account or is granted cap_net_raw capability using setcap");
                    _pingParams.IsAdmin = true;
                }
                else
                {
                    _logger.LogWarning(" Unable to send custom ping payload. Run program under privileged user account or grant cap_net_raw capability using setcap.");
                    _pingParams.IsAdmin = false;
                }
                _monitorPingInfos = AddMonitorPingInfos(initObj.MonitorIPs, currentMonitorPingInfos);
                _netConnects = _connectFactory.GetNetConnectList(_monitorPingInfos, _pingParams);

                _logger.LogDebug("MonitorPingInfos : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                _logger.LogDebug("MonitorIPs : " + JsonUtils.writeJsonObjectToString(initObj.MonitorIPs));
                _logger.LogDebug("PingParams : " + JsonUtils.writeJsonObjectToString(_pingParams));

                ProcessorInitObj processorObj = new ProcessorInitObj();
                processorObj.AppID = _appID;
                processorObj.IsProcessorReady = true;

                //_daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "processorReady", processorObj, _daprMetadata);
                DaprRepo.PublishEvent<ProcessorInitObj>(_daprClient, "processorReady", processorObj);

                _logger.LogInformation("Published event ProcessorItitObj.IsProcessorReady = true");

            }
            catch (Exception e)
            {
                _logger.LogCritical("Error : Unable to init Processor : Error was : " + e.ToString());

            }

        }

        public void PublishMonitorPingInfos(bool saveState)
        {

            var cutMonitorPingInfos = _monitorPingInfos.ConvertAll(x => new MonitorPingInfo(x));
            var pingInfos = new List<PingInfo>();
            _monitorPingInfos.ForEach(f => pingInfos.AddRange(f.PingInfos));
            var processorDataObj = new ProcessorDataObj();
            processorDataObj.MonitorPingInfos = cutMonitorPingInfos;
             processorDataObj.PingInfos=pingInfos;
            //processorDataObj.PingInfos = new List<PingInfo>();
            _logger.LogDebug("Publishing ProcessorDataObj : " + JsonUtils.writeJsonObjectToString(processorDataObj));
            DaprRepo.PublishEvent<ProcessorDataObj>(_daprClient, "monitorUpdateMonitorPingInfos", processorDataObj);
            DaprRepo.PublishEvent<List<MonitorPingInfo>>(_daprClient, "alertUpdateMonitorPingInfos", cutMonitorPingInfos);


            string logStr = "Published to MonitorService and AlertService.";
            var m = _monitorPingInfos.FirstOrDefault(w => w.Enabled == true);
            if (m != null && m.PingInfos != null)
            {
                logStr += " Count of first enabled PingInfos " + _monitorPingInfos.Where(w => w.Enabled == true).First().PingInfos.Count() + " .";
            }
            else
            {
                logStr += " Found no first enabled PingInfos .";
            }

            if (saveState)
            {
                DaprRepo.SaveState<ProcessorDataObj>(_daprClient, "ProcessorDataObj", processorDataObj);
                logStr += " Saved MonitorPingInfos to State.";
            }
            _logger.LogInformation(logStr);
        }

        private List<MonitorPingInfo> AddMonitorPingInfos(List<MonitorIP> monitorIPs, List<MonitorPingInfo> currentMonitorPingInfos)
        {
            var monitorPingInfos = new List<MonitorPingInfo>();
            int i = 0;
            foreach (MonitorIP monIP in monitorIPs)
            {

                MonitorPingInfo monitorPingInfo = currentMonitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);

                if (monitorPingInfo != null)
                {
                    _logger.LogDebug("Updatating MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    //monitorPingInfo.MonitorStatus.MonitorPingInfo = null;
                    //monitorPingInfo.MonitorStatus.MonitorPingInfoID = 0;
                }
                else
                {
                    monitorPingInfo = new MonitorPingInfo();
                    monitorPingInfo.MonitorIPID = monIP.ID;
                    _logger.LogDebug("Adding new MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    monitorPingInfo.ID = monIP.ID;
                    monitorPingInfo.UserID = monIP.UserInfo.UserID;

                }
                fillPingInfo(monitorPingInfo, monIP);
                monitorPingInfos.Add(monitorPingInfo);
                i++;
            }
            return monitorPingInfos;

        }

        private void fillPingInfo(MonitorPingInfo monitorPingInfo, MonitorIP monIP)
        {
            monitorPingInfo.ID = monIP.ID;
            monitorPingInfo.AppID = _appID;
            monitorPingInfo.Address = monIP.Address;
            monitorPingInfo.Enabled = monIP.Enabled;
            monitorPingInfo.EndPointType = monIP.EndPointType;
            //monitorPingInfo.MonitorStatus.MonitorPingInfo = null;
            //monitorPingInfo.MonitorStatus.MonitorPingInfoID = 0;

            if (monIP.Timeout == 0)
            {
                monitorPingInfo.Timeout = _pingParams.Timeout;
            }
            else
            {
                monitorPingInfo.Timeout = monIP.Timeout;
            }
            return;

        }
        private Task GetNetConnect(int monitorPingInfoID)
        {
            var connectTask = _netConnects.FirstOrDefault(w => w.MonitorPingInfo.ID == monitorPingInfoID);
            // return completed task if no netConnect found
            if (connectTask == null) return Task.FromResult<object>(null);
            return connectTask.connect();
        }
        public ResultObj Connect(ProcessorConnectObj connectObj)
        {
            _logger.LogDebug("ProcessorConnectObj : " + JsonUtils.writeJsonObjectToString(connectObj));

            var processorObj = new ProcessorInitObj();
            processorObj.IsProcessorReady = false;
            processorObj.AppID = _appID;
            //_daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "processorReady", processorObj, _daprMetadata);
            DaprRepo.PublishEvent<ProcessorInitObj>(_daprClient, "processorReady", processorObj);

            _logger.LogInformation("Published event ProcessorItitObj.IsProcessorReady = false");


            var result = new ResultObj();
            result.Success = false;
            result.Message = "SERVICE : MonitorPingProcessor.Connect() ";
            _logger.LogInformation("SERVICE : MonitorPingProcessor.Connect() ");

            // Process the queue of user host updates
            result.Message += UpdateMonitorPingInfosFromMonitorIPQueue();

            if (_monitorPingInfos == null || _monitorPingInfos.Where(x => x.Enabled == true).Count() == 0)
            {

                result.Message += "Warning : There is no MonitorPingInfo data.";
                _logger.LogWarning("Warning : There is no MonitorPingInfo data.");
                result.Success = false;
                return result;
            }
            // Time interval between Now and NextRun
            int executionTime = connectObj.NextRunInterval - _pingParams.Timeout - connectObj.MaxBuffer;
            int timeToWait = executionTime / _monitorPingInfos.Where(x => x.Enabled == true).Count();
            if (timeToWait < 25)
            {
                result.Message += "Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings.";
                _logger.LogWarning("Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings.");
            }
            result.Message += "Info : Time to wait : " + timeToWait + "ms ";

            try
            {
                var pingConnectTasks = new List<Task>();
                var timerInner = new Stopwatch();
                var timerDec = new Stopwatch();
                TimeSpan timeTakenDec;
                timerInner.Start();
                foreach (var netConnect in _netConnects.Where(w => w.MonitorPingInfo.Enabled == true))
                {
                    timerDec.Start();
                    pingConnectTasks.Add(netConnect.connect());
                    timerDec.Stop();
                    timeTakenDec = timerDec.Elapsed;
                    int timeTakenDecMilliseconds = (int)timeTakenDec.TotalMilliseconds;
                    int diff = timeToWait - timeTakenDecMilliseconds;
                     if (diff > 0)
                    {
                        Thread.Sleep(diff);
                    }
                    timerDec.Reset();
                }
                Task.WhenAll(pingConnectTasks);
                Thread.Sleep(_pingParams.Timeout + 100);
                bool isDaprReady = _daprClient.CheckHealthAsync().Result;
                if (isDaprReady)
                {
                    if (_monitorPingInfos.Count > 0)
                    {
                        _monitorPingInfos.Where(w => w.PingInfos!=null).ToList().ForEach(f => f.PacketsSent=f.PingInfos.Count());
                        PublishMonitorPingInfos(true);
                    }
                    else
                    {
                        _logger.LogError("There are no MonitorPingInfos after first connect run");

                    }

                }
                else
                {
                    _logger.LogError("Dapr Client Status is not healthy");
                    if (_monitorPingInfos.Count > 0)
                    {
                        _logger.LogError("There are MonitorPingInfos that need to be saved to statestore");
                    }
                }

                TimeSpan timeTakenInner = timerInner.Elapsed;
                // If time taken is greater than the time to wait, then we need to adjust the time to wait.
                int timeTakenInnerInt = (int)timeTakenInner.TotalMilliseconds;
                if (timeTakenInnerInt > connectObj.NextRunInterval)
                {
                    result.Message += "Warning : Time to execute greater than next schedule time ";
                    _logger.LogWarning("Warning : Time to execute greater than next schedule time ");
                }

                result.Message += "Success : MonitorPingProcessor.Connect Executed in " + timeTakenInnerInt + " ms";

                result.Success = true;
                timerInner.Reset();


            }
            catch (Exception e)
            {
                result.Message += "Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString();
                result.Success = false;
                _logger.LogError("Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString());
            }
            finally
            {
                try
                {
                    processorObj.IsProcessorReady = true;
                    processorObj.AppID = _appID;
                    //_daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "processorReady", processorObj, _daprMetadata);
                    DaprRepo.PublishEvent<ProcessorInitObj>(_daprClient, "processorReady", processorObj);

                    _logger.LogInformation("Published event ProcessorItitObj.IsProcessorReady = true");

                }
                catch (Exception ex)
                {
                    _logger.LogCritical("Error : Failed to publish processorReady = true, processing will stop . Error was : " + ex.Message.ToString());

                }
            }
            return result;
        }
        private string UpdateMonitorPingInfosFromMonitorIPQueue()
        {
            ProcessMonitorIPDic();
            if (_monitorIPQueue.Count == 0) return "Info : No updates in monitorIP queue to process"; ;

            List<MonitorIP> monitorIPs = _monitorIPQueue;
            // Get max MonitorPingInfo.ID
            int maxID = _monitorPingInfos.Max(m => m.ID);
            string message = "Success : Updated Host List";
            //Add and update
            foreach (MonitorIP monIP in monitorIPs)
            {
                MonitorPingInfo monitorPingInfo = _monitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);

                // If monitorIP is contained in the list of monitorPingInfos then update it.
                if (monitorPingInfo != null)
                {
                    try
                    {
                        if (monitorPingInfo.Address != monIP.Address || monitorPingInfo.EndPointType != monIP.EndPointType || (monitorPingInfo.Enabled == false && monIP.Enabled == true))
                        {
                            fillPingInfo(monitorPingInfo, monIP);
                            NetConnect netConnect = _netConnects.FirstOrDefault(w => w.MonitorPingInfo.ID == monitorPingInfo.ID);
                            if (netConnect != null)
                            {
                                int index = _netConnects.IndexOf(netConnect);
                                NetConnect newNetConnect = _connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams);
                                _netConnects[index] = newNetConnect;
                            }
                            else
                            {
                                // recreate if it is missing
                                _netConnects.Add(_connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams));
                            }

                        }
                        else
                        {
                            NetConnect netConnect = _netConnects.FirstOrDefault(w => w.MonitorPingInfo.ID == monitorPingInfo.ID);
                            fillPingInfo(monitorPingInfo, monIP);
                            if (netConnect != null)
                            {
                                netConnect.MonitorPingInfo = monitorPingInfo;
                            }
                            else
                            {
                                // recreate if its missing
                                _netConnects.Add(_connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams));
                            }

                        }
                    }
                    catch
                    {
                        message = "Error : Failed to update Host list check Values.";
                    }
                }
                // Else create a new MonitorPingInfo
                else
                {
                    monitorPingInfo = new MonitorPingInfo();
                    maxID++;
                    monitorPingInfo.MonitorIPID = monIP.ID;
                    monitorPingInfo.ID = maxID;
                    monitorPingInfo.UserID = monIP.UserID;
                    fillPingInfo(monitorPingInfo, monIP);
                    _monitorPingInfos.Add(monitorPingInfo);
                    NetConnect netConnect = _connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams);
                    _netConnects.Add(netConnect);
                }
            }

            //Delete
            List<MonitorPingInfo> delList = new List<MonitorPingInfo>();
            foreach (MonitorPingInfo del in _monitorPingInfos)
            {
                if (monitorIPs.Where(m => m.ID == del.MonitorIPID).Count() == 0)
                {
                    if (monitorIPs.Where(m => m.UserID == del.UserID).Count() > 0)
                    {
                        delList.Add(del);
                    }
                }
            }
            foreach (MonitorPingInfo del in delList)
            {
                _monitorPingInfos.Remove(del);
            }

            // reset queue to empty
            _monitorIPQueue = new List<MonitorIP>();

            return message;

        }
        public void AddMonitorIPsToQueueDic(ProcessorQueueDicObj queueDicObj)
        {
            // Nothing to process so just return
            if (queueDicObj.MonitorIPs.Count == 0) return;
            // replace any existing monitorIPs with the same userId
            _monitorIPQueueDic.Remove(queueDicObj.UserId);
            _monitorIPQueueDic.Add(queueDicObj.UserId, queueDicObj.MonitorIPs);
        }

        private void ProcessMonitorIPDic()
        {
            // Get all MonitorIPs from the queue
            foreach (KeyValuePair<string, List<MonitorIP>> kvp in _monitorIPQueueDic)
            {
                _monitorIPQueue.AddRange(kvp.Value);
            }
            // Reset Queue Dictionary
            _monitorIPQueueDic = new Dictionary<string, List<MonitorIP>>();
        }

        public List<ResultObj> UpdateAlertSent(List<int> monitorPingInfoIDs, bool alertSent)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorPingInfoIDs)
            {
                var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.ID == id);
                var result = new ResultObj();
                if (updateMonitorPingInfo != null)
                {
                    updateMonitorPingInfo.MonitorStatus.AlertSent = alertSent;
                    result.Success = true;
                    result.Message += "Success : updated AlertSent to " + alertSent + " for MonitorPingInfo ID = " + updateMonitorPingInfo.ID;

                }
                else
                {
                    result.Success = false;
                    result.Message += "Failed : updating AlertSent for MonitorPingInfo ID = " + updateMonitorPingInfo.ID;

                }
                results.Add(result);
            }
            return results;
        }
        public List<ResultObj> UpdateAlertFlag(List<int> monitorPingInfoIDs, bool alertFlag)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorPingInfoIDs)
            {
                var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.ID == id);
                var result = new ResultObj();
                if (updateMonitorPingInfo != null)
                {
                    updateMonitorPingInfo.MonitorStatus.AlertFlag = alertFlag;
                    result.Success = true;
                    result.Message += "Success : updated AlertFlag to " + alertFlag + " for MonitorPingInfo ID = " + updateMonitorPingInfo.ID;

                }
                else
                {
                    result.Success = false;
                    result.Message += "Failed : updating AlertFlag for MonitorPingInfo ID = " + updateMonitorPingInfo.ID;

                }
                results.Add(result);
            }
            return results;
        }

        public ResultObj ResetAlert(int monitorPingInfoId)
        {
            var result = new ResultObj();
            var alertFlagObj = new AlertFlagObj();
            alertFlagObj.ID = monitorPingInfoId; ;
            alertFlagObj.AppID = _appID;
            var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.ID == alertFlagObj.ID && w.AppID == alertFlagObj.AppID);

            if (updateMonitorPingInfo == null)
            {
                result.Success = false;
                result.Message += "Warning : Unable to find MonitorPingInfo with ID " + alertFlagObj.ID + " with AppID " + alertFlagObj.AppID;
            }
            else
            {
                updateMonitorPingInfo.MonitorStatus.AlertFlag = false;
                updateMonitorPingInfo.MonitorStatus.AlertSent = false;
                updateMonitorPingInfo.MonitorStatus.DownCount = 0;

                result.Success = true;
                result.Message += "Success : updated MonitorPingInfo with ID " + alertFlagObj.ID + " with AppID " + alertFlagObj.AppID;
            }

            try
            {
                //_daprClient.PublishEventAsync<AlertFlagObj>("pubsub", "alertMessageResetAlert", alertFlagObj, _daprMetadata);
                DaprRepo.PublishEvent<AlertFlagObj>(_daprClient, "alertMessageResetAlert", alertFlagObj);

            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += "Error : failed to set alertMessageResetAlert. Error was :" + e.Message.ToString();

            }

            return result;
        }
    }

}