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
using System.Runtime;
using System.Diagnostics;
using MetroLog;
using MetroLog.Maui;
using MetroLog.MicrosoftExtensions;
using MetroLog.Targets;
using MetroLog.Internal;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
namespace NetworkMonitor.Processor.Services
{
    public class MonitorPingProcessor : IMonitorPingProcessor
    {
        private readonly object _lock = new object();
        private bool _awake;
        private ILogger _logger;
           private string _appID = "1";
        private PingParams _pingParams;
        private List<int> _removeMonitorPingInfoIDs = new List<int>();
        private List<SwapMonitorPingInfo> _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
       
        private NetConnectCollection _netConnectCollection;
        private MonitorPingCollection _monitorPingCollection;
        private Dictionary<string, List<UpdateMonitorIP>> _monitorIPQueueDic = new Dictionary<string, List<UpdateMonitorIP>>();
        // private List<MonitorIP> _monitorIPQueue = new List<MonitorIP>();
        //private DaprClient _daprClient;
        private uint _piIDKey = 1;
        private RabbitListener _rabbitRepo;
        public bool Awake { get => _awake; set => _awake = value; }
        public MonitorPingProcessor(IConfiguration config, ILogger logger, IConnectFactory connectFactory)
        {
            _logger = logger;
            
            FileRepo.CheckFileExists("ProcessorDataObj", logger);
            FileRepo.CheckFileExists("MonitorIPs", logger);
            FileRepo.CheckFileExists("PingParams", logger);
            _appID = config.GetValue<string>("AppID");
            SystemUrl systemUrl = config.GetSection("SystemUrl").Get<SystemUrl>() ?? throw new ArgumentNullException("SystemUrl");
            _logger.Info(" Starting Processor with AppID = " + _appID + " instanceName=" + systemUrl.RabbitInstanceName + " connecting to RabbitMQ at " + systemUrl.RabbitHostName + ":" + systemUrl.RabbitPort);
            _rabbitRepo = new RabbitListener(_logger, systemUrl, this, _appID);
            _netConnectCollection = new NetConnectCollection(_logger, config, connectFactory);
            _monitorPingCollection = new MonitorPingCollection(_logger);
            Init(new ProcessorInitObj());
        }
        public void OnStopping()
        {
            _logger.Warn("PROCESSOR SHUTDOWN : starting shutdown of MonitorPingService");
            try
            {
                _logger.Info(" Saving MonitorPingInfos to state");
                PublishRepo.MonitorPingInfos(_logger, _rabbitRepo, _monitorPingCollection.MonitorPingInfos.ToList(), _removeMonitorPingInfoIDs, null, _swapMonitorPingInfos, _appID, _piIDKey, true);
                _logger.Debug("MonitorPingInfos StateStore : " + JsonUtils.writeJsonObjectToString(_monitorPingCollection.MonitorPingInfos));
                _logger.Info(" Sending ProcessorReady = false");
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, false);
                // Cancel all the tasks
                _logger.Info(" Cancelling all tasks");
                _netConnectCollection.CancelAllTasks();
                // DaprRepo.PublishEvent<ProcessorInitObj>(_daprClient, "processorReady", processorObj);
                _logger.Info("Published event ProcessorItitObj.IsProcessorReady = false");
                _logger.Warn("PROCESSOR SHUTDOWN : Complete");
            }
            catch (Exception e)
            {
                _logger.Fatal("Error : Failed to run SaveState before shutdown : Error Was : " + e.ToString());
                Console.WriteLine();
            }
        }
        /*
        The method init(ProcessorInitObj initObj) initializes the state of the program by either resetting the state store or loading the previous state from it. If the initObj.TotalReset flag is set to true, the state store is completely reset, and new empty objects are saved to the state store. If initObj.Reset is set to true, the state of the MonitorPingInfos object is zeroed, and the current state of this object is saved. If neither flag is set, the previous state of the objects is loaded from the state store. The loaded state includes MonitorPingInfos, RemoveMonitorPingInfoIDs, SwapMonitorPingInfos, RemovePingInfos, and PiIDKey. The method uses the FileRepo class to interact with the state store. If any errors occur during the loading or resetting of the state store, an error message is logged.*/
        public void Init(ProcessorInitObj initObj)
        {
            _netConnectCollection.Init();
            List<MonitorPingInfo> currentMonitorPingInfos;
            List<MonitorIP> stateMonitorIPs = new List<MonitorIP>();
            PingParams statePingParams = new PingParams();
            _monitorPingCollection.RemovePingInfos = new List<RemovePingInfo>();
            _removeMonitorPingInfoIDs = new List<int>();
            try
            {
                //bool isDaprReady = _daprClient.CheckHealthAsync().Result;
                if (initObj.TotalReset)
                {
                    _logger.Info("Resetting Processor MonitorPingInfos in statestore");
                    var processorDataObj = new ProcessorDataObj()
                    {
                        MonitorPingInfos = new List<MonitorPingInfo>(),
                        RemoveMonitorPingInfoIDs = new List<int>(),
                        SwapMonitorPingInfos = new List<SwapMonitorPingInfo>(),
                        RemovePingInfos = new List<RemovePingInfo>(),
                        PingInfos = new List<PingInfo>(),
                        PiIDKey = 1
                    };
                    currentMonitorPingInfos = new List<MonitorPingInfo>();
                    try
                    {
                        FileRepo.SaveStateJsonZ("ProcessorDataObj", processorDataObj);
                        FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", new List<MonitorIP>());
                        FileRepo.SaveStateJsonZ<PingParams>("PingParams", new PingParams());
                        _logger.Info("Reset Processor Objects in statestore ");
                    }
                    catch (Exception e)
                    {
                        _logger.Error("Error : Could not reset Processor Objects to statestore. Error was : " + e.Message.ToString());
                    }
                }
                else
                {
                    if (initObj.Reset)
                    {
                        _logger.Info("Zeroing MonitorPingInfos for new DataSet");
                        foreach (MonitorPingInfo monitorPingInfo in _monitorPingCollection.MonitorPingInfos)
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
                        currentMonitorPingInfos = _monitorPingCollection.MonitorPingInfos.ToList();
                        _piIDKey = 1;
                    }
                    else
                    {
                        string infoLog = "";
                        try
                        {
                            using (var processorDataObj = FileRepo.GetStateStringJsonZ<ProcessorDataObj>("ProcessorDataObj"))
                            {
                                _piIDKey = processorDataObj.PiIDKey;
                                infoLog += " Got PiIDKey=" + _piIDKey + " . ";
                                currentMonitorPingInfos = ProcessorDataBuilder.Build(processorDataObj);
                                _removeMonitorPingInfoIDs = processorDataObj.RemoveMonitorPingInfoIDs;
                                _monitorPingCollection.RemovePingInfos = processorDataObj.RemovePingInfos;
                                _swapMonitorPingInfos = processorDataObj.SwapMonitorPingInfos;
                                if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                                if (_monitorPingCollection.RemovePingInfos == null) _monitorPingCollection.RemovePingInfos = new List<RemovePingInfo>();
                                if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
                            }
                            if (currentMonitorPingInfos.Where(w => w.Enabled == true).FirstOrDefault() != null)
                            {
                                infoLog += (" Success : Building MonitorPingInfos from ProcessorDataObj in statestore. First Enabled PingInfo Count = " + currentMonitorPingInfos.Where(w => w.Enabled == true).FirstOrDefault().PingInfos.Count()) + " ";
                            }
                            else
                            {
                                _logger.Warn("Warning : MonitorPingInfos from ProcessorDataObj in statestore contains no Data .");
                            }
                        }
                        catch (Exception)
                        {
                            _logger.Error("Error : Building MonitorPingInfos from ProcessorDataObj in statestore");
                            currentMonitorPingInfos = new List<MonitorPingInfo>();
                            if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                            if (_monitorPingCollection.RemovePingInfos == null) _monitorPingCollection.RemovePingInfos = new List<RemovePingInfo>();
                            if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
                        }
                        try
                        {
                            stateMonitorIPs = FileRepo.GetStateJsonZ<List<MonitorIP>>("MonitorIPs");
                            if (stateMonitorIPs != null) infoLog += (" Got MonitorIPS from statestore count =" + stateMonitorIPs.Count()) + " . ";
                        }
                        catch (Exception e)
                        {
                            _logger.Warn("Warning : Could get MonitorIPs from statestore. Error was : " + e.Message.ToString());
                        }
                        try
                        {
                            statePingParams = FileRepo.GetStateJsonZ<PingParams>("PingParams");
                            infoLog += ("Got PingParams from statestore . ");
                        }
                        catch (Exception e)
                        {
                            _logger.Warn("Warning : Could get PingParms from statestore. Error was : " + e.Message.ToString());
                        }
                        _logger.Info(infoLog);
                    }
                }
            }
            catch (Exception e)
            {
                _logger.Error("Failed : Loading statestore : Error was : " + e.ToString());
                currentMonitorPingInfos = new List<MonitorPingInfo>();
            }
            try
            {
                if (initObj.MonitorIPs == null || initObj.MonitorIPs.Count == 0)
                {
                    _logger.Warn("Warning : There are No MonitorIPs using statestore");
                    initObj.MonitorIPs = stateMonitorIPs;
                    if (stateMonitorIPs == null || stateMonitorIPs.Count == 0)
                    {
                        _logger.Error("Error : There are No MonitorIPs in statestore");
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
                        _logger.Error(" Error : Unable to Save MonitorIPs to statestore. Error was : " + e.Message);
                    }
                }
                if (initObj.PingParams == null)
                {
                    _logger.Warn("Warning : There are No PingParams using statestore");
                    _pingParams = statePingParams;
                    if (statePingParams == null)
                    {
                        _logger.Error("Error : There are No PingParams in statestore");
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
                        if (_pingParams == null) _pingParams = new PingParams();
                        _logger.Error(" Error : Unable to Save PingParams to statestore. Error was : " + e.Message);
                    }
                }
                if (SystemParamsHelper.IsSystemElevatedPrivilege)
                {
                    _logger.Info("Ping Payload can be customised.  Program is running under privileged user account or is granted cap_net_raw capability using setcap");
                    if (_pingParams != null) _pingParams.IsAdmin = true;
                }
                else
                {
                    _logger.Warn(" Unable to send custom ping payload. Run program under privileged user account or grant cap_net_raw capability using setcap.");
                    if (_pingParams != null) _pingParams.IsAdmin = false;
                }
                _monitorPingCollection.SetVars(_appID,_pingParams);
                _monitorPingCollection.MonitorPingInfoFactory(initObj.MonitorIPs, currentMonitorPingInfos);
                _netConnectCollection.NetConnectFactory(_monitorPingCollection.MonitorPingInfos.ToList(), _pingParams);
                _logger.Debug("MonitorPingInfos : " + JsonUtils.writeJsonObjectToString(_monitorPingCollection.MonitorPingInfos));
                _logger.Debug("MonitorIPs : " + JsonUtils.writeJsonObjectToString(initObj.MonitorIPs));
                _logger.Debug("PingParams : " + JsonUtils.writeJsonObjectToString(_pingParams));
                PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, _monitorPingCollection.MonitorPingInfos.ToList(), _removeMonitorPingInfoIDs, null, _swapMonitorPingInfos, _appID, _piIDKey, false);
            }
            catch (Exception e)
            {
                _logger.Fatal("Error : Unable to init Processor : Error was : " + e.ToString());
            }
            finally
            {
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, true);
                _netConnectCollection.IsLocked = false;
            }
        }
        // This method is used to connect to remote hosts by creating and executing NetConnect objects. 
        public async Task<ResultObj> Connect(ProcessorConnectObj connectObj)
        {
            _awake = true;
            while (_netConnectCollection.IsLocked){
                _logger.Warn("Warning : NetConnectCollection is locked. Waiting 1 second to try again.");
                await Task.Delay(1000);
            }
            var timerInner = new Stopwatch();
            timerInner.Start();
            _logger.Debug(" ProcessorConnectObj : " + JsonUtils.writeJsonObjectToString(connectObj));
            PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, false);
            var result = new ResultObj();
            result.Success = false;
            result.Message = " SERVICE : MonitorPingProcessor.Connect() ";
            _logger.Info(" SERVICE : MonitorPingProcessor.Connect() ");
            try
            {
                result.Message += UpdateMonitorPingInfosFromMonitorIPQueue();
            }
            catch (Exception e)
            {
                result.Message = " Error : Failed to Process Monitor IP Queue. Error was : " + e.Message.ToString() + " . ";
                _logger.Error(" Error : Failed to Process Monitor IP Queue. Error was : " + e.ToString() + " . ");
            }
            if (_monitorPingCollection.MonitorPingInfos == null || _monitorPingCollection.MonitorPingInfos.Where(x => x.Enabled == true).Count() == 0)
            {
                result.Message += " Warning : There is no MonitorPingInfo data. ";
                _logger.Warn(" Warning : There is no MonitorPingInfo data. ");
                result.Success = false;
                _awake = false;
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, true);
                return result;
            }
            try
            {
                var pingConnectTasks = new List<Task>();
                result.Message += " MEMINFO Before : " + GC.GetGCMemoryInfo().TotalCommittedBytes + " : ";
                GC.Collect();
                result.Message += " MEMINFO After : " + GC.GetGCMemoryInfo().TotalCommittedBytes + " : ";
                GC.TryStartNoGCRegion(104857600, false);
                var filteredNetConnects = _netConnectCollection.GetFilteredNetConnects().Where(w => w.MonitorPingInfo.Enabled == true).ToList();
                // Time interval between Now and NextRun
                int executionTime = connectObj.NextRunInterval - connectObj.MaxBuffer;
                int timeToWait = executionTime / filteredNetConnects.Count();
                if (timeToWait < 25)
                {
                    result.Message += " Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ";
                    _logger.Warn(" Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ");
                }
                result.Message += " Info : Time to wait : " + timeToWait + "ms. ";
                int countDown = filteredNetConnects.Count();
                foreach (var netConnect in filteredNetConnects)
                {
                    netConnect.PiID = _piIDKey;
                    _piIDKey++;
                    if (netConnect.IsLongRunning)
                    {
                        //Console.WriteLine($"Starting long running task for MonitorIPID {netConnect.MonitorPingInfo.MonitorIPID}");
                        _ = _netConnectCollection.HandleLongRunningTask(netConnect); // Call the new method to handle long-running tasks without awaiting it
                    }
                    else
                    {
                        pingConnectTasks.Add(netConnect.Connect());
                    }
                    await Task.Delay(timeToWait); // Use 'await' here
                                                  // recalculate the timeToWait based on the timmerInner.Elapsed and countDown
                    if (countDown < 1) countDown = 1;
                    timeToWait = (executionTime - (int)timerInner.ElapsedMilliseconds) / countDown;
                    if (timeToWait < 0)
                    {
                        timeToWait = 0;
                        _logger.Warn(" Warning : Time to wait is less than 0ms.  This may cause problems with the service.  Please check the schedule settings. ");
                    }
                    countDown--;
                };
                if (GCSettings.LatencyMode == GCLatencyMode.NoGCRegion)
                    GC.EndNoGCRegion();
                //new System.Threading.ManualResetEvent(false).WaitOne(_pingParams.Timeout);
                result.Message += " Success : Completed all NetConnect tasks in " + timerInner.Elapsed.TotalMilliseconds + " ms ";
                result.Success = true;
                // Check _netConnectCollection for any NetConnects that have RunningTime > _maxRunningTime and log them.
                result.Message += _netConnectCollection.LogInfo(filteredNetConnects);
            }
            catch (Exception e)
            {
                result.Message += " Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ";
                result.Success = false;
                _logger.Fatal(" Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ");
            }
            finally
            {
                if (_monitorPingCollection.MonitorPingInfos.Count > 0)
                {
                    result.Message += _monitorPingCollection.RemovePublishedPingInfos().Message;
                    PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, _monitorPingCollection.MonitorPingInfos.ToList(), _removeMonitorPingInfoIDs, _monitorPingCollection.RemovePingInfos, _swapMonitorPingInfos, _appID, _piIDKey, true);
                }
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, true);
            }
            int timeTakenInnerInt = (int)timerInner.Elapsed.TotalMilliseconds;
            if (timeTakenInnerInt > connectObj.NextRunInterval)
            {
                result.Message += " Warning : Time to execute greater than next schedule time. ";
                _logger.Warn(" Warning : Time to execute greater than next schedule time. ");
            }
            result.Message += " Success : MonitorPingProcessor.Connect Executed in " + timerInner.Elapsed.TotalMilliseconds + " ms ";
            _awake = false;
            return result;
        }
        //This method updates the MonitorPingInfo list with new information from the UpdateMonitorIP queue. The queue is processed and any new or updated information is added to the MonitorPingInfo list and a corresponding NetConnect object is created or updated in the _netConnects list. Deleted items are removed from the MonitorPingInfo list. This method uses the _logger to log information about the updates.
        private string UpdateMonitorPingInfosFromMonitorIPQueue()
        {
            // lock the rest of the method
            lock (_lock)
            {
                var monitorIPQueue = new List<UpdateMonitorIP>();
                if (_monitorIPQueueDic.Count() == 0) return " No Data in Queue . ";
                foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
                {
                    if (!kvp.Value[0].DeleteAll)
                    {
                        kvp.Value.ForEach(f =>
                        {
                            if (!f.Delete) monitorIPQueue.Add(f);
                        });
                    }
                }
                // Reset Queue Dictionary
                //if (monitorIPQueue.Count == 0) return "Info : No updates in monitorIP queue to process"; ;
                // Get max MonitorPingInfo.ID
                //int maxID = MonitorPingInfos.Max(m => m.ID);
                string message = "";
                List<UpdateMonitorIP> addBackMonitorIPs = new List<UpdateMonitorIP>();
                //Add and update
                foreach (UpdateMonitorIP monIP in monitorIPQueue)
                {
                    var monitorPingInfo = _monitorPingCollection.MonitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);
                    // If monitorIP is contained in the list of monitorPingInfos then update it.
                    if (monitorPingInfo != null)
                    {
                        // We are not going to process if the NetConnect is still running.
                        if (_netConnectCollection.IsNetConnectRunning(monitorPingInfo.ID))
                        {
                            message += " Error : NetConnect with MonitorPingInfoID " + monitorPingInfo.ID + " is still running. ";
                            addBackMonitorIPs.Add(monIP);
                            continue;
                        }
                        try
                        {
                            if (monitorPingInfo.Port != monIP.Port || monitorPingInfo.Address != monIP.Address || monitorPingInfo.EndPointType != monIP.EndPointType || (monitorPingInfo.Enabled == false && monIP.Enabled == true))
                            {
                                _monitorPingCollection.FillPingInfo(monitorPingInfo, monIP);
                                message += _netConnectCollection.ReplaceOrAdd(monitorPingInfo, _pingParams);
                            }
                            else
                            {
                                _monitorPingCollection.FillPingInfo(monitorPingInfo, monIP);
                                _netConnectCollection.UpdateOrAdd(monitorPingInfo, _pingParams);
                            }
                        }
                        catch
                        {
                            message += "Error : Failed to update Host list check Values.";
                        }
                        _logger.Info(" Updating MonitorPingInfo with ID " + monitorPingInfo.ID);
                    }
                    // Else create a new MonitorPingInfo or copy from Queue
                    else
                    {
                        if (!monIP.IsSwapping || monIP.MonitorPingInfo == null)
                        {
                            monitorPingInfo = new MonitorPingInfo();
                            monitorPingInfo.MonitorIPID = monIP.ID;
                            monitorPingInfo.ID = monIP.ID;
                            monitorPingInfo.UserID = monIP.UserID; ;
                            _monitorPingCollection.FillPingInfo(monitorPingInfo, monIP);
                            _logger.Info(" Just adding a new MonitorPingInfo with ID " + monitorPingInfo.ID);
                        }
                        else
                        {
                            monitorPingInfo = monIP.MonitorPingInfo;
                            monitorPingInfo.AppID = _appID;
                            _swapMonitorPingInfos.Add(new SwapMonitorPingInfo()
                            {
                                ID = monitorPingInfo.ID,
                                AppID = _appID
                            });
                            _logger.Info(" Adding SwapMonitorPingInfo with ID " + monitorPingInfo.ID);
                        }
                        _monitorPingCollection.MonitorPingInfos.Add(monitorPingInfo);
                        _netConnectCollection.Add(monitorPingInfo, _pingParams);
                    }
                }
                //Delete
                List<MonitorPingInfo> delList = new List<MonitorPingInfo>();
                foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
                {
                    kvp.Value.ForEach(f =>
                        {
                            // Skip if monitorIP is in addBackMonitorIPs ie NetConnect still running
                            if (!addBackMonitorIPs.Contains(f) && f.Delete)
                            {
                                var del = _monitorPingCollection.MonitorPingInfos.Where(w => w.MonitorIPID == f.ID).FirstOrDefault();
                                delList.Add(del);
                                _logger.Info(" Deleting MonitorIP with ID " + f.ID);
                                if (!f.IsSwapping) _removeMonitorPingInfoIDs.Add(del.MonitorIPID);
                            }
                        });
                }
                foreach (MonitorPingInfo del in delList)
                {
                    var removeMon = new MonitorPingInfo(del);
                    if (!_monitorPingCollection.MonitorPingInfos.TryTake(out removeMon))
                    {
                        message += " Error : Failed to remove MonitorPingInfo with ID " + removeMon.ID + " . ";
                        _logger.Error(" Error : Failed to remove MonitorPingInfo with ID " + removeMon.ID + " . ");
                    }
                }
                message += " Success : Updated MonitorPingInfos. ";
                // Update statestore with new MonitorIPs
                // remove addBackMonitorIPs from monitorIPQueue
                monitorIPQueue.RemoveAll(addBackMonitorIPs.Contains);
                message += UpdateMonitorIPsInStatestore(monitorIPQueue);
                // remove all items from queue that are no in addBackMonitorIPs
                foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
                {
                    kvp.Value.RemoveAll(r => !addBackMonitorIPs.Contains(r));
                }
                // remove all empty keys
                _monitorIPQueueDic = _monitorIPQueueDic.Where(w => w.Value.Count > 0).ToDictionary(d => d.Key, d => d.Value);
                return message;
            }
        }
        public void ProcessesMonitorReturnData(ProcessorDataObj processorDataObj)
        {
            if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
            if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
            if (_monitorPingCollection.RemovePingInfos == null) _monitorPingCollection.RemovePingInfos = new List<RemovePingInfo>();
            _monitorPingCollection.RemovePingInfos.AddRange(processorDataObj.RemovePingInfos);
            processorDataObj.RemoveMonitorPingInfoIDs.ForEach(f =>
            {
                _removeMonitorPingInfoIDs.Remove(f);
            });
            if (processorDataObj.SwapMonitorPingInfos != null) processorDataObj.SwapMonitorPingInfos.ForEach(f =>
            {
                _swapMonitorPingInfos.Remove(f);
            });
        }
        private string UpdateMonitorIPsInStatestore(List<UpdateMonitorIP> updateMonitorIPs)
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
                        stateMonitorIPs.Add((MonitorIP)updateMonitorIP);
                    }
                    else
                    {
                        stateMonitorIPs.Remove(monitorIP);
                        stateMonitorIPs.Add((MonitorIP)updateMonitorIP);
                    }
                }
                foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
                {
                    kvp.Value.ForEach(f =>
                    {
                        if (f.Delete) stateMonitorIPs.RemoveAll(r => r.ID == f.ID);
                    });
                }
                FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", stateMonitorIPs);
                resultStr += " Success : saved MonitorIP queue into statestore. ";
            }
            catch (Exception e)
            {
                _logger.Error("Error : Failed to update MonitorIP queue to statestore. Error was : " + e.Message.ToString());
                throw e;
            }
            return resultStr;
        }
        //This method "UpdateMonitorPingInfosFromMonitorIPQueue()" updates the information in the "MonitorPingInfo" class from a queue of updates stored in "_monitorIPQueueDic". 
        public void AddMonitorIPsToQueueDic(ProcessorQueueDicObj queueDicObj)
        {
            // Nothing to process so just return
            if (queueDicObj.MonitorIPs.Count == 0) return;
            // replace any existing monitorIPs with the same userId
            _monitorIPQueueDic.Remove(queueDicObj.UserId);
            _monitorIPQueueDic.Add(queueDicObj.UserId, queueDicObj.MonitorIPs);
        }
        // This method updates the AlertSent property of MonitorPingInfo objects in the MonitorPingInfos list, based on the provided monitorIPIDs list. For each id in monitorIPIDs, it retrieves the corresponding MonitorPingInfo object and sets its AlertSent property to alertSent. The method returns a list of ResultObj objects, where each object represents the result of updating the AlertSent property for a specific MonitorPingInfo object.
        public List<ResultObj> UpdateAlertSent(List<int> monitorIPIDs, bool alertSent)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorIPIDs)
            {
                var updateMonitorPingInfo = _monitorPingCollection.MonitorPingInfos.FirstOrDefault(w => w.MonitorIPID == id);
                var result = new ResultObj();
                if (updateMonitorPingInfo != null)
                {
                    updateMonitorPingInfo.MonitorStatus.AlertSent = alertSent;
                    result.Success = true;
                    result.Message += "Success : updated AlertSent to " + alertSent + " for MonitorPingInfo with MonitorIPID = " + id;
                }
                else
                {
                    result.Success = false;
                    result.Message += "Failed : updating AlertSent for MonitorPingInfo with MonitorIPID = " + id;
                }
                results.Add(result);
            }
            return results;
        }
        // This method updates the AlertFlag field for multiple MonitorPingInfo objects based on the provided monitorIPIDs. The method returns a list of ResultObj objects indicating the success or failure of the update for each MonitorPingInfo. If the MonitorPingInfo with a given id is found in the MonitorPingInfos collection, the AlertFlag field is updated to the provided alertFlag value, and a success message is added to the ResultObj. If the MonitorPingInfo is not found, a failure message is added to the ResultObj.
        public List<ResultObj> UpdateAlertFlag(List<int> monitorIPIDs, bool alertFlag)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorIPIDs)
            {
                var updateMonitorPingInfo = _monitorPingCollection.MonitorPingInfos.FirstOrDefault(w => w.MonitorIPID == id);
                var result = new ResultObj();
                if (updateMonitorPingInfo != null)
                {
                    updateMonitorPingInfo.MonitorStatus.AlertFlag = alertFlag;
                    result.Success = true;
                    result.Message += "Success : updated AlertFlag to " + alertFlag + " for MonitorPingInfo with MonitorIPID = " + id;
                }
                else
                {
                    result.Success = false;
                    result.Message += "Failed : updating AlertFlag for MonitorPingInfo with MonitorIPID = " + id;
                }
                results.Add(result);
            }
            return results;
        }
        // This method resets the alert status for a list of MonitorPingInfos, specified by their monitorIPIDs, by setting the AlertFlag to false and AlertSent to false, and setting the DownCount to 0. It also publishes a message "alertMessageResetAlerts" with the list of AlertFlagObjs to the rabbitmq. The method returns a list of ResultObjs, which contains the success or failure of the operation and the relevant message.
        public List<ResultObj> ResetAlerts(List<int> monitorIPIDs)
        {
            var results = new List<ResultObj>();
            ResultObj result;
            var alertFlagObjs = new List<AlertFlagObj>();
            monitorIPIDs.ForEach(m =>
            {
                result = new ResultObj();
                var alertFlagObj = new AlertFlagObj();
                alertFlagObj.ID = m;
                alertFlagObj.AppID = _appID;
                alertFlagObjs.Add(alertFlagObj);
                var updateMonitorPingInfo = _monitorPingCollection.MonitorPingInfos.FirstOrDefault(w => w.MonitorIPID == alertFlagObj.ID && w.AppID == alertFlagObj.AppID);
                if (updateMonitorPingInfo == null)
                {
                    result.Success = false;
                    result.Message += " Warning : Unable to find MonitorPingInfo with MonitorIPID " + alertFlagObj.ID + " with AppID " + alertFlagObj.AppID + " . ";
                }
                else
                {
                    updateMonitorPingInfo.MonitorStatus.AlertFlag = false;
                    updateMonitorPingInfo.MonitorStatus.AlertSent = false;
                    updateMonitorPingInfo.MonitorStatus.DownCount = 0;
                    result.Success = true;
                    result.Message += " Success : updated MonitorPingInfo with MonitorIPID " + alertFlagObj.ID + " with AppID " + alertFlagObj.AppID + " . ";
                }
                results.Add(result);
            });
            results.Add(PublishRepo.AlertMessgeResetAlerts(_rabbitRepo, alertFlagObjs));
            return results;
        }
        public ResultObj WakeUp()
        {
            ResultObj result = new ResultObj();
            result.Message = "SERVICE : MonitorPingProcessor.WakeUp() ";
            try
            {
                if (_awake)
                {
                    result.Message += "Received WakeUp but processor is currently running";
                    result.Success = false;
                }
                else
                {
                    PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, true);
                    result.Message += "Received WakeUp so Published event processorReady = true";
                    result.Success = true;
                }
            }
            catch (Exception e)
            {
                result.Message += "Error : failed to Published event processorReady = true. Error was : " + e.ToString();
                result.Success = false;
            }
            return result;
        }

        public async Task WaitInit(ProcessorInitObj initObj){
            _netConnectCollection.IsLocked=true;
            while (_awake){
                await Task.Delay(1000);
            }
            Init(initObj);
        }
    }
}