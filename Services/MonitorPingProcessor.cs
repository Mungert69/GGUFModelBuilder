using System;
using System.Collections.Generic;
using NetworkMonitor.Objects;
using NetworkMonitor.Utils;
using NetworkMonitor.Objects.ServiceMessage;
using System.Linq;
using NetworkMonitor.Connection;
using System.Threading.Tasks;
using System.Threading;
using System.Diagnostics;
using Dapr.Client;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Hosting;

namespace NetworkMonitorProcessor.Services
{

    public class MonitorPingProcessor : IMonitorPingProcessor
    {
        private PingParams _pingParams;

        private ILogger _logger;
        private List<NetConnect> _netConnects = null;
        private Dictionary<string, List<MonitorIP>> _monitorIPQueueDic = new Dictionary<string, List<MonitorIP>>();
        private List<MonitorIP> _monitorIPQueue = new List<MonitorIP>();
        private DaprClient _daprClient;

        private List<MonitorPingInfo> _monitorPingInfos = new List<MonitorPingInfo>();

        public MonitorPingProcessor(ILogger<MonitorPingProcessor> logger, DaprClient daprClient, IHostApplicationLifetime appLifetime)
        {
            appLifetime.ApplicationStopping.Register(OnStopping);
            _logger = logger;
            _daprClient = daprClient;
            init(new ProcessorInitObj());
        }

        private void OnStopping()
        {
            Console.WriteLine("PROCESSOR SHUTDOWN : starting shutdown of MonitorPingService");
            try
            {
                _daprClient.SaveStateAsync<List<MonitorPingInfo>>("statestore", "MonitorPingInfos", _monitorPingInfos);
                _daprClient.PublishEventAsync<List<MonitorPingInfo>>("pubsub", "monitorUpdateMonitorPingInfos", _monitorPingInfos);

                _logger.LogDebug("MonitorPingInfos StateStore : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                _logger.LogInformation("Saved to state MonitorPingInfos to StateStore and Publish Event monitorUpdateMonitorPingInfos");

                ProcessorInitObj processorObj = new ProcessorInitObj();
                processorObj.IsProcessorStarted = false;
                _daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "monitorIsProcessorStarted", processorObj);
                _logger.LogInformation("Published event ProcessorItitObj.IsProcessorStarted = false");

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
                        _logger.LogInformation("Resetting Processor MonitorPingInfos");
                        _daprClient.SaveStateAsync<List<MonitorPingInfo>>("statestore", "MonitorPingInfos", new List<MonitorPingInfo>());
                        currentMonitorPingInfos=new List<MonitorPingInfo>();
                        _logger.LogInformation("Reset MonitorPingInfos in statestore ");
                    }
                    else
                    {
                        if (initObj.Reset)
                        {
                            _logger.LogInformation("Zeroing MonitorPingInfos for new DataSet");
                            foreach (MonitorPingInfo monitorPingInfo in _monitorPingInfos)
                            {
                                monitorPingInfo.PacketsLost = 0;
                                monitorPingInfo.PacketsLostPercentage = 0;
                                monitorPingInfo.PacketsRecieved = 0;
                                monitorPingInfo.PacketsSent = 0;
                                monitorPingInfo.PingInfos = new List<PingInfo>();
                                monitorPingInfo.RoundTripTimeAverage = 0;
                                monitorPingInfo.RoundTripTimeMaximum = 0;
                                monitorPingInfo.RoundTripTimeMinimum = 0;
                                monitorPingInfo.RoundTripTimeTotal = 0;
                                monitorPingInfo.TimeOuts = 0;
                            }
                            currentMonitorPingInfos = _monitorPingInfos;
                        }
                        else
                        {

                            statePingParams = _daprClient.GetStateAsync<PingParams>("statestore", "PingParams").Result;
                            _logger.LogInformation("PingParams from statestore ");

                            stateMonitorIPs = _daprClient.GetStateAsync<List<MonitorIP>>("statestore", "MonitorIPs").Result;
                            _logger.LogInformation("MonitorIPS from statestore count =" + stateMonitorIPs.Count);

                            currentMonitorPingInfos = _daprClient.GetStateAsync<List<MonitorPingInfo>>("statestore", "MonitorPingInfos").Result;
                            _logger.LogInformation("MonitorPingInfos from statestore count of first enabled PingInfos " + currentMonitorPingInfos.Where(w => w.Enabled == true).First().PingInfos.Count());
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
                _logger.LogError("Failed : State Store : Error was : " + e.ToString());
                currentMonitorPingInfos = new List<MonitorPingInfo>();
            }


            try
            {
                if (initObj.MonitorIPs == null || initObj.MonitorIPs.Count == 0)
                {
                    _logger.LogWarning("Warning : There are No MonitorIPs using State Store");
                    initObj.MonitorIPs = stateMonitorIPs;
                    if (stateMonitorIPs.Count == 0)
                    {
                        _logger.LogError("Error : There are No MonitorIPs in State Store");
                    }
                }
                else
                {
                    _daprClient.SaveStateAsync<List<MonitorIP>>("statestore", "MonitorIPs", initObj.MonitorIPs);
                }
                if (initObj.PingParams == null)
                {
                    _logger.LogWarning("Warning : There are No PingParams using State Store");
                    _pingParams = statePingParams;
                    if (statePingParams == null)
                    {
                        _logger.LogError("Error : There are No PingParams in State Store");
                    }
                }
                else
                {
                    _daprClient.SaveStateAsync<PingParams>("statestore", "PingParams", initObj.PingParams);
                    _pingParams = initObj.PingParams;
                }

                _monitorPingInfos = AddMonitorPingInfos(initObj.MonitorIPs, currentMonitorPingInfos);
                _netConnects = ConnectFactory.GetNetConnectList(_monitorPingInfos, _pingParams);

                _logger.LogDebug("MonitorPingInfos : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                _logger.LogDebug("MonitorIPs : " + JsonUtils.writeJsonObjectToString(initObj.MonitorIPs));
                _logger.LogDebug("PingParams : " + JsonUtils.writeJsonObjectToString(_pingParams));

                ProcessorInitObj processorObj = new ProcessorInitObj();
                if (_monitorPingInfos.Count > 0)
                {
                    processorObj.IsProcessorStarted = true;
                    _daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "monitorIsProcessorStarted", processorObj);
                    _logger.LogInformation("Published event ProcessorItitObj.IsProcessorStarted = true");

                }
                else
                {
                    processorObj.IsProcessorStarted = false;
                    _daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "monitorIsProcessorStarted", processorObj);
                    _logger.LogError("Error : Unable to init Processor");

                }
            }
            catch (Exception e)
            {
                _logger.LogCritical("Error : Unable to init Processor : Error was : " + e.ToString());

            }

        }


        private List<MonitorPingInfo> AddMonitorPingInfos(List<MonitorIP> monitorIPs, List<MonitorPingInfo> currentMonitorPingInfos)
        {
            List<MonitorPingInfo> monitorPingInfos = new List<MonitorPingInfo>();
            int i = 0;
            foreach (MonitorIP monIP in monitorIPs)
            {

                MonitorPingInfo monitorPingInfo = new MonitorPingInfo();
                int count = currentMonitorPingInfos.Where(m => m.MonitorIPID == monIP.ID).Count();
                if (count > 0)
                {
                    monitorPingInfo = currentMonitorPingInfos.Where(m => m.MonitorIPID == monIP.ID).First();
                    _logger.LogDebug("Updatating MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    //monitorPingInfo.MonitorStatus.MonitorPingInfo = null;
                    //monitorPingInfo.MonitorStatus.MonitorPingInfoID = 0;
                }
                else
                {
                    monitorPingInfo.MonitorIPID = monIP.ID;
                    _logger.LogDebug("Adding new MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    monitorPingInfo.ID = i + 1;
                    monitorPingInfo.UserID = monIP.UserInfo.UserID;


                    /*// Reteive previous MonitorStatus if in memory.
                    if (currentMonitorPingInfos.Where(w => w.MonitorIPID == monIP.ID).Count() > 0)
                    {
                        monitorPingInfo.MonitorStatus = currentMonitorPingInfos.Where(w => w.MonitorIPID == monIP.ID).First().MonitorStatus;
                        //monitorPingInfo.MonitorStatus.MonitorPingInfo = null;
                        //monitorPingInfo.MonitorStatus.MonitorPingInfoID = 0;
                    }*/
                }
                fillPingInfo(monitorPingInfo, monIP);
                monitorPingInfos.Add(monitorPingInfo);
                i++;
            }
            return monitorPingInfos;

        }

        private void fillPingInfo(MonitorPingInfo monitorPingInfo, MonitorIP monIP)
        {

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
            return _netConnects.Where(w => w.MonitorPingInfo.ID == monitorPingInfoID).FirstOrDefault().connect();
        }
        public ResultObj Connect(ProcessorConnectObj connectObj)
        {
            _logger.LogDebug("ProcessorConnectObj : " + JsonUtils.writeJsonObjectToString(connectObj));

            ResultObj result = new ResultObj();
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
                //ProcessorInitObj processorObj = new ProcessorInitObj();
                //processorObj.IsProcessorStarted = false;
                //_daprClient.PublishEventAsync<ProcessorInitObj>("pubsub", "monitorProcessorStart", processorObj);
                return result;
            }
            // Time interval between Now and NextRun
            int executionTime = connectObj.NextRunInterval - _pingParams.Timeout - connectObj.MaxBuffer;
            int timeToWait = executionTime / _monitorPingInfos.Where(x => x.Enabled == true).Count();
            if (timeToWait < 10)
            {
                result.Message += "Warning : Time to wait is less than 10ms.  This may cause problems with the service.  Please check the schedule settings.";
                _logger.LogWarning("Warning : Time to wait is less than 10ms.  This may cause problems with the service.  Please check the schedule settings.");
            }
            result.Message += "Info : Time to wait : " + timeToWait + "ms ";

            try
            {
                PingParams pingParams = _pingParams;
                List<Task> pingConnectTasks = new List<Task>();
                Stopwatch timerInner = new Stopwatch();
                Stopwatch timerDec = new Stopwatch();
                TimeSpan timeTakenDec;
                timerInner.Start();
                foreach (MonitorPingInfo monitorPingInfo in _monitorPingInfos.Where(x => x.Enabled == true))
                {

                    timerDec.Start();
                    Task pingConnect = GetNetConnect(monitorPingInfo.ID);
                    pingConnectTasks.Add(pingConnect);

                    // pause for the time to wait
                    timerDec.Stop();
                    timeTakenDec = timerDec.Elapsed;
                    int timeTakenDecMilliseconds = (int)timeTakenDec.TotalMilliseconds;
                    int diff = timeToWait - timeTakenDecMilliseconds;
                    //                    Console.WriteLine("Info : Time taken to connect : " + timeTakenDecMilliseconds + "ms ");
                    if (diff > 0)
                    {
                        Thread.Sleep(diff);
                    }
                    timerDec.Reset();

                }
                Thread.Sleep(_pingParams.Timeout+connectObj.MaxBuffer/2);
                Task.WhenAll(pingConnectTasks);
                pingConnectTasks.Clear();
                //ListUtils.RemoveNestedMonitorPingInfos(_monitorPingInfos);
                bool isDaprReady = _daprClient.CheckHealthAsync().Result;
                if (isDaprReady)
                {
                    _logger.LogInformation("Dapr Client Status is healthy");
                    _daprClient.SaveStateAsync<List<MonitorPingInfo>>("statestore", "MonitorPingInfos", _monitorPingInfos);
                    _daprClient.PublishEventAsync<List<MonitorPingInfo>>("pubsub", "monitorUpdateMonitorPingInfos", _monitorPingInfos);
                    _logger.LogDebug("MonitorPingInfos StateStore : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                    _logger.LogInformation("Saved MonitorPingInfos to StateStore and Publish Event monitorUpdateMonitorPingInfos");
                    _logger.LogInformation("Number of PingInfos in first enabled MonitorPingInfos is " + _monitorPingInfos.Where(w => w.Enabled == true).First().PingInfos.Count());

                }
                else
                {
                    _logger.LogError("Dapr Client Status is not healthy");
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
                result.Message += "Error : MonitorPingProcessor.Ping Failed : Error Was : " + e.ToString();
                result.Success = false;
                _logger.LogError("Error : MonitorPingProcessor.Ping Failed : Error Was : " + e.ToString());
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
                MonitorPingInfo monitorPingInfo = new MonitorPingInfo();

                int count = _monitorPingInfos.Where(m => m.MonitorIPID == monIP.ID).Count();
                // If monitorIP is contained in the list of monitorPingInfos then update it.
                if (count > 0)
                {
                    try
                    {
                        monitorPingInfo = _monitorPingInfos.Where(m => m.MonitorIPID == monIP.ID).First();
                        if (monitorPingInfo.Address != monIP.Address || monitorPingInfo.EndPointType != monIP.EndPointType || (monitorPingInfo.Enabled == false && monIP.Enabled == true))
                        {
                            fillPingInfo(monitorPingInfo, monIP);
                            NetConnect netConnect = _netConnects.Where(w => w.MonitorPingInfo.ID == monitorPingInfo.ID).First();
                            int index = _netConnects.IndexOf(netConnect);
                            NetConnect newNetConnect = ConnectFactory.GetNetConnectObj(monitorPingInfo, _pingParams);
                            _netConnects[index] = newNetConnect;
                        }
                        else
                        {
                            NetConnect netConnect = _netConnects.Where(w => w.MonitorPingInfo.ID == monitorPingInfo.ID).First();
                            fillPingInfo(monitorPingInfo, monIP);
                            netConnect.MonitorPingInfo = monitorPingInfo;
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
                    maxID++;
                    monitorPingInfo.MonitorIPID = monIP.ID;
                    monitorPingInfo.ID = maxID;
                    monitorPingInfo.UserID = monIP.UserID;
                    fillPingInfo(monitorPingInfo, monIP);
                    _monitorPingInfos.Add(monitorPingInfo);
                    NetConnect netConnect = ConnectFactory.GetNetConnectObj(monitorPingInfo, _pingParams);
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

        public void UpdateAlertSent(List<int> monitorPingInfoIDs, bool alertSent)
        {
            foreach (int id in monitorPingInfoIDs)
            {
                _monitorPingInfos.Where(w => w.ID == id).First().MonitorStatus.AlertSent = alertSent;

            }
        }
        public void UpdateAlertFlag(List<int> monitorPingInfoIDs, bool alertFlag)
        {
            foreach (int id in monitorPingInfoIDs)
            {
                _monitorPingInfos.Where(w => w.ID == id).First().MonitorStatus.AlertFlag = alertFlag;

            }
        }

        public void ResetAlert(int monitorPingInfoId)
        {

            _monitorPingInfos.Where(m => m.ID == monitorPingInfoId).FirstOrDefault().MonitorStatus.AlertFlag = false;
            _monitorPingInfos.Where(m => m.ID == monitorPingInfoId).FirstOrDefault().MonitorStatus.AlertSent = false;
            _monitorPingInfos.Where(m => m.ID == monitorPingInfoId).FirstOrDefault().MonitorStatus.DownCount = 0;

        }
    }

}