using System;
using System.Collections.Generic;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
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
        private bool _awake;
        private ILogger _logger;
        private List<NetConnect> _netConnects = null;
        private Dictionary<string, List<MonitorIP>> _monitorIPQueueDic = new Dictionary<string, List<MonitorIP>>();
        private List<MonitorIP> _monitorIPQueue = new List<MonitorIP>();
        private DaprClient _daprClient;
        private string _appID = "1";
        private int _piIDKey = 1;
        private List<RemovePingInfo> _removePingInfos = new List<RemovePingInfo>();
        private IConnectFactory _connectFactory;
        private List<MonitorPingInfo> _monitorPingInfos = new List<MonitorPingInfo>();
        public bool Awake { get => _awake; set => _awake = value; }
        public MonitorPingProcessor(IConfiguration config, ILogger<MonitorPingProcessor> logger, DaprClient daprClient, IHostApplicationLifetime appLifetime, IConnectFactory connectFactory)
        {
            appLifetime.ApplicationStopping.Register(OnStopping);
            _logger = logger;
            _daprClient = daprClient;
            // Special case 2min timeout for large published messages.
            _appID = config.GetValue<string>("AppID");
            _connectFactory = connectFactory;
            init(new ProcessorInitObj());
        }
        private void OnStopping()
        {
            Console.WriteLine("PROCESSOR SHUTDOWN : starting shutdown of MonitorPingService");
            try
            {
                PublishRepo.MonitorPingInfos(_logger, _daprClient, _monitorPingInfos, _appID, _piIDKey, true);
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
                            PingInfos = new List<PingInfo>(),
                            PiIDKey = 1
                        };
                        currentMonitorPingInfos = new List<MonitorPingInfo>();
                        try
                        {
                            FileRepo.SaveStateJsonZ("ProcessorDataObj", processorDataObj);
                            FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", new List<MonitorIP>());
                            FileRepo.SaveStateJsonZ<PingParams>("PingParams", new PingParams());
                            _logger.LogInformation("Reset Processor Objects in statestore ");
                        }
                        catch (Exception e)
                        {
                            _logger.LogError("Error : Could not reset Processor Objects to statestore. Error was : " + e.Message.ToString());
                        }
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
                                //monitorPingInfo.TimeOuts = 0;
                            }
                            currentMonitorPingInfos = _monitorPingInfos;
                            _piIDKey = 1;
                        }
                        else
                        {
                            string infoLog = "";
                            try
                            {
                                using (var processorDataObj = FileRepo.GetStateJsonZ<ProcessorDataObj>("ProcessorDataObj"))
                                {
                                    _piIDKey = processorDataObj.PiIDKey;
                                    infoLog += " Got PiIDKey=" + _piIDKey + " . ";
                                    currentMonitorPingInfos = ProcessorDataBuilder.Build(processorDataObj);
                                }
                                if (currentMonitorPingInfos.Where(w => w.Enabled == true).FirstOrDefault() != null)
                                {
                                    infoLog += (" Success : Building MonitorPingInfos from ProcessorDataObj in statestore. First Enabled PingInfo Count = " + currentMonitorPingInfos.Where(w => w.Enabled == true).FirstOrDefault().PingInfos.Count()) + " ";
                                }
                                else
                                {
                                    _logger.LogWarning("Warning : MonitorPingInfos from ProcessorDataObj in statestore contains no Data .");
                                }
                            }
                            catch (Exception)
                            {
                                _logger.LogError("Error : Building MonitorPingInfos from ProcessorDataObj in statestore");
                                currentMonitorPingInfos = new List<MonitorPingInfo>();
                            }
                            try
                            {
                                stateMonitorIPs = FileRepo.GetStateJsonZ<List<MonitorIP>>("MonitorIPs");
                                if (stateMonitorIPs != null) infoLog += (" Got MonitorIPS from statestore count =" + stateMonitorIPs.Count()) + " . ";
                            }
                            catch (Exception e)
                            {
                                _logger.LogWarning("Warning : Could get MonitorIPs from statestore. Error was : " + e.Message.ToString());
                            }
                            try
                            {
                                statePingParams = FileRepo.GetStateJsonZ<PingParams>("PingParams");
                                infoLog += ("Got PingParams from statestore . ");
                            }
                            catch (Exception e)
                            {
                                _logger.LogWarning("Warning : Could get PingParms from statestore. Error was : " + e.Message.ToString());
                            }
                            _logger.LogInformation(infoLog);
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
                    try
                    {
                        FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", initObj.MonitorIPs);
                    }
                    catch (Exception e)
                    {
                        _logger.LogError(" Error : Unable to Save MonitorIPs to statestore. Error was : " + e.Message);
                    }
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
                    _pingParams = initObj.PingParams;
                    try
                    {
                        FileRepo.SaveStateJsonZ<PingParams>("PingParams", initObj.PingParams);
                    }
                    catch (Exception e)
                    {
                        _logger.LogError(" Error : Unable to Save OingParams to statestore. Error was : " + e.Message);
                    }
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
                _removePingInfos = new List<RemovePingInfo>();
                _monitorPingInfos = AddMonitorPingInfos(initObj.MonitorIPs, currentMonitorPingInfos);
                _netConnects = _connectFactory.GetNetConnectList(_monitorPingInfos, _pingParams);
                _logger.LogDebug("MonitorPingInfos : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                _logger.LogDebug("MonitorIPs : " + JsonUtils.writeJsonObjectToString(initObj.MonitorIPs));
                _logger.LogDebug("PingParams : " + JsonUtils.writeJsonObjectToString(_pingParams));
                PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _daprClient, _monitorPingInfos, _appID, _piIDKey, false);
                PublishRepo.ProcessorReadyThread(_logger, _daprClient, _appID, true);
            }
            catch (Exception e)
            {
                _logger.LogCritical("Error : Unable to init Processor : Error was : " + e.ToString());
            }
        }
        public void AddRemovePingInfos(List<RemovePingInfo> removePingInfos)
        {
            _removePingInfos.AddRange(removePingInfos);
        }
        private ResultObj removePublishedPingInfos()
        {
            var result=new ResultObj();
            int count=0;
            if (_removePingInfos == null || _removePingInfos.Count() == 0 || _monitorPingInfos==null || _monitorPingInfos.Count()==0 ) {
                result.Success=false;
                result.Message=" No PingInfos removed. ";
                return result;
            } 
            _monitorPingInfos.ForEach(f =>
            {
                _removePingInfos.Where(w => w.MonitorPingInfoID == f.ID).ToList().ForEach(p =>
                {
                    f.PingInfos.RemoveAll(r => r.ID == p.ID);
                    count++;
                });
                _removePingInfos.RemoveAll(r => r.MonitorPingInfoID == f.ID);
            });
            result.Success=true;
            result.Message=" Removed "+count+" PingInfos from MonitorPingInfos. ";
            return result;
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
                    monitorPingInfo.UserID = monIP.UserID;
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
            var timerInner = new Stopwatch();
            timerInner.Start();
            _logger.LogDebug(" ProcessorConnectObj : " + JsonUtils.writeJsonObjectToString(connectObj));
            PublishRepo.ProcessorReadyThread(_logger, _daprClient, _appID, false);
            var result = new ResultObj();
            result.Success = false;
            result.Message = " SERVICE : MonitorPingProcessor.Connect() ";
            _logger.LogInformation(" SERVICE : MonitorPingProcessor.Connect() ");
            try
            {
                result.Message += UpdateMonitorPingInfosFromMonitorIPQueue();
            }
            catch (Exception e)
            {
                result.Message = " Error : Failed to Process Monitor IP Queue. Error was : " + e.Message.ToString() + " . ";
                _logger.LogError(" Error : Failed to Process Monitor IP Queue. Error was : " + e.Message.ToString() + " . ");
            }
            if (_monitorPingInfos == null || _monitorPingInfos.Where(x => x.Enabled == true).Count() == 0)
            {
                result.Message += " Warning : There is no MonitorPingInfo data. ";
                _logger.LogWarning(" Warning : There is no MonitorPingInfo data. ");
                result.Success = false;
                return result;
            }
            // Time interval between Now and NextRun
            int executionTime = connectObj.NextRunInterval - _pingParams.Timeout - connectObj.MaxBuffer;
            int timeToWait = executionTime / _monitorPingInfos.Where(x => x.Enabled == true).Count();
            if (timeToWait < 25)
            {
                result.Message += " Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ";
                _logger.LogWarning(" Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ");
            }
            result.Message += " Info : Time to wait : " + timeToWait + "ms. ";
            try
            {
                var pingConnectTasks = new List<Task>();
                _netConnects.Where(w => w.MonitorPingInfo.Enabled == true).ToList().ForEach(
                    netConnect =>
                    {
                        netConnect.PiID = _piIDKey;
                        _piIDKey++;
                        pingConnectTasks.Add(netConnect.connect());
                        new System.Threading.ManualResetEvent(false).WaitOne(timeToWait);
                    }
                );
                Task.WhenAll(pingConnectTasks.ToArray());
                new System.Threading.ManualResetEvent(false).WaitOne(_pingParams.Timeout);
                result.Message += " Success : Completed all NetConnect tasks in " + timerInner.Elapsed.TotalMilliseconds + " ms ";
                result.Success = true;
            }
            catch (Exception e)
            {
                result.Message += " Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ";
                result.Success = false;
                _logger.LogCritical(" Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ");
            }
            finally
            {
                if (_monitorPingInfos.Count > 0)
                {
                    result.Message+= removePublishedPingInfos().Message;
                    PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _daprClient, _monitorPingInfos, _appID, _piIDKey, true);
                }
                PublishRepo.ProcessorReadyThread(_logger, _daprClient, _appID, true);
            }
            int timeTakenInnerInt = (int)timerInner.Elapsed.TotalMilliseconds;
            if (timeTakenInnerInt > connectObj.NextRunInterval)
            {
                result.Message += " Warning : Time to execute greater than next schedule time. ";
                _logger.LogWarning(" Warning : Time to execute greater than next schedule time. ");
            }
            result.Message += " Success : MonitorPingProcessor.Connect Executed in " + timerInner.Elapsed.TotalMilliseconds + " ms ";
            return result;
        }
        private string UpdateMonitorPingInfosFromMonitorIPQueue()
        {
            ProcessMonitorIPDic();
            if (_monitorIPQueue.Count == 0) return "Info : No updates in monitorIP queue to process"; ;
            List<MonitorIP> monitorIPs = _monitorIPQueue;
            // Get max MonitorPingInfo.ID
            int maxID = _monitorPingInfos.Max(m => m.ID);
            string message = "";
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
                        message += "Error : Failed to update Host list check Values.";
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
            message += " Success : Updated MonitorPingInfos. ";
            // Update statestore with new MonitorIPs
            message += UpdateMonitorIPsInStatestore(_monitorIPQueue);
            // reset queue to empty
            _monitorIPQueue = new List<MonitorIP>();
            return message;
        }
        private string UpdateMonitorIPsInStatestore(List<MonitorIP> updateMonitorIPs)
        {
            string resultStr = "";
            try
            {
                var stateMonitorIPs = FileRepo.GetStateJsonZ<List<MonitorIP>>("MonitorIPs");
                foreach (var updateMonitorIP in updateMonitorIPs)
                {
                    var monitorIP = stateMonitorIPs.Where(w => w.ID == updateMonitorIP.ID).FirstOrDefault();
                    if (monitorIP == null)
                    {
                        stateMonitorIPs.Add(updateMonitorIP);
                    }
                    else
                    {
                        stateMonitorIPs.Remove(monitorIP);
                        stateMonitorIPs.Add(updateMonitorIP);
                    }
                }
                FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", stateMonitorIPs);
                resultStr += " Success : saved MonitorIP queue into statestore. ";
            }
            catch (Exception e)
            {
                _logger.LogError("Error : Failed to update MonitorIP queue to statestore. Error was : " + e.Message.ToString());
                throw e;
            }
            return resultStr;
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
        public ResultObj ResetAlert(int monitorIPID)
        {
            var result = new ResultObj();
            var alertFlagObj = new AlertFlagObj();
            alertFlagObj.ID = monitorIPID; ;
            alertFlagObj.AppID = _appID;
            var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.MonitorIPID == alertFlagObj.ID && w.AppID == alertFlagObj.AppID);
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