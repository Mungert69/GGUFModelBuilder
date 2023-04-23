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
namespace NetworkMonitor.Processor.Services
{
    public class MonitorPingProcessor : IMonitorPingProcessor
    {
        private PingParams _pingParams;
        private bool _awake;
        private ILogger _logger;
        private NetConnectCollection _netConnectCollection;

        private SemaphoreSlim _taskSemaphore; // Limit to 5 concurrent tasks

        private int _waitingTasksCounter = 0;
        private int  _maxTaskQueueSize=100;
        private List<int> _quantumTaskQueueIDs = new  List<int>();
        private List<int> _longRunningTaskIDs = new  List<int>();


        private Dictionary<string, List<UpdateMonitorIP>> _monitorIPQueueDic = new Dictionary<string, List<UpdateMonitorIP>>();
        // private List<MonitorIP> _monitorIPQueue = new List<MonitorIP>();
        //private DaprClient _daprClient;
        private string _appID = "1";
        private uint _piIDKey = 1;
        private RabbitListener _rabbitRepo;
        private List<RemovePingInfo> _removePingInfos = new List<RemovePingInfo>();
        private IConnectFactory _connectFactory;
        private List<MonitorPingInfo> _monitorPingInfos = new List<MonitorPingInfo>();
        private List<int> _removeMonitorPingInfoIDs = new List<int>();
        private List<SwapMonitorPingInfo> _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
        public bool Awake { get => _awake; set => _awake = value; }
        public MonitorPingProcessor(IConfiguration config, ILogger logger, IConnectFactory connectFactory)
        {
            _logger = logger;
            
            FileRepo.CheckFileExists("ProcessorDataObj", logger);
            FileRepo.CheckFileExists("MonitorIPs", logger);
            FileRepo.CheckFileExists("PingParams", logger);

            _appID = config.GetValue<string>("AppID");
            _connectFactory = connectFactory;
            SystemUrl systemUrl = config.GetSection("SystemUrl").Get<SystemUrl>() ?? throw new ArgumentNullException("SystemUrl");
            _logger.Info(" Starting Processor with AppID = " + _appID + " instanceName=" + systemUrl.RabbitInstanceName + " connecting to RabbitMQ at " + systemUrl.RabbitHostName + ":" + systemUrl.RabbitPort);

            _rabbitRepo = new RabbitListener(_logger, systemUrl, this, _appID);
            int quantumFilterSkip=config.GetValue<int>("QuantumFilterSkip");
            int quantumFilterStart=config.GetValue<int>("QuantumFilterStart");
            int smtpFilterSkip=config.GetValue<int>("SmtpFilterSkip");
            int smtpFilterStart=config.GetValue<int>("SmtpFilterStart");
            _maxTaskQueueSize=config.GetValue<int>("MaxTaskQueueSize");
            _taskSemaphore= new SemaphoreSlim(_maxTaskQueueSize);
            _logger.Info("QuantumFilterSkip = " + quantumFilterSkip + " QuantumFilterStart = " + quantumFilterStart + " SmtpFilterSkip = " + smtpFilterSkip + " SmtpFilterStart = " + smtpFilterStart + " MaxTaskQueueSize = " + _maxTaskQueueSize);
           
            INetConnectFilterStrategy quantumStrategy = new QuantumEndpointFilterStrategy(quantumFilterSkip, quantumFilterStart);
            INetConnectFilterStrategy smtpStrategy = new SmtpEndPointFilterStrategy(smtpFilterSkip, smtpFilterStart);

            // Combine the strategies using the composite pattern
            INetConnectFilterStrategy compositeStrategy = new CompositeFilterStrategy(quantumStrategy, smtpStrategy);

            // Create an instance of the NetConnectCollection with the composite strategy
            _netConnectCollection = new NetConnectCollection(compositeStrategy);

            init(new ProcessorInitObj());
        }
        public void OnStopping()
        {
            _logger.Warn("PROCESSOR SHUTDOWN : starting shutdown of MonitorPingService");
            try
            {
                PublishRepo.MonitorPingInfos(_logger, _rabbitRepo, _monitorPingInfos, _removeMonitorPingInfoIDs, null, _swapMonitorPingInfos, _appID, _piIDKey, true);
                _logger.Debug("MonitorPingInfos StateStore : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, false);
                // DaprRepo.PublishEvent<ProcessorInitObj>(_daprClient, "processorReady", processorObj);
                _logger.Info("Published event ProcessorItitObj.IsProcessorReady = false");
                _logger.Warn("PROCESSOR SHUTDOWN : Complete");
            }
            catch (Exception e)
            {
                _logger.Fatal("Error : Failed to run SaveState before shutdown : Error Was : " + e.ToString() + " Inner Exception : " + e.InnerException.Message);
                Console.WriteLine();
            }
        }
        /*
        The method init(ProcessorInitObj initObj) initializes the state of the program by either resetting the state store or loading the previous state from it. If the initObj.TotalReset flag is set to true, the state store is completely reset, and new empty objects are saved to the state store. If initObj.Reset is set to true, the state of the MonitorPingInfos object is zeroed, and the current state of this object is saved. If neither flag is set, the previous state of the objects is loaded from the state store. The loaded state includes MonitorPingInfos, RemoveMonitorPingInfoIDs, SwapMonitorPingInfos, RemovePingInfos, and PiIDKey. The method uses the FileRepo class to interact with the state store. If any errors occur during the loading or resetting of the state store, an error message is logged.*/
        public void init(ProcessorInitObj initObj)
        {
            List<MonitorPingInfo> currentMonitorPingInfos;
            List<MonitorIP> stateMonitorIPs = new List<MonitorIP>();
            PingParams statePingParams = new PingParams();
            _removePingInfos = new List<RemovePingInfo>();
            _removeMonitorPingInfoIDs = new List<int>();
            try
            {
                //bool isDaprReady = _daprClient.CheckHealthAsync().Result;
                if (initObj.TotalReset)
                {
                    _logger.Info("Resetting Processor MonitorPingInfos in statestore");
                    Dictionary<string, string> metadata = new Dictionary<string, string>();
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
                            using (var processorDataObj = FileRepo.GetStateStringJsonZ<ProcessorDataObj>("ProcessorDataObj"))
                            {
                                _piIDKey = processorDataObj.PiIDKey;
                                infoLog += " Got PiIDKey=" + _piIDKey + " . ";
                                currentMonitorPingInfos = ProcessorDataBuilder.Build(processorDataObj);
                                _removeMonitorPingInfoIDs = processorDataObj.RemoveMonitorPingInfoIDs;
                                _removePingInfos = processorDataObj.RemovePingInfos;
                                _swapMonitorPingInfos = processorDataObj.SwapMonitorPingInfos;
                                if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                                if (_removePingInfos == null) _removePingInfos = new List<RemovePingInfo>();
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
                            if (_removePingInfos == null) _removePingInfos = new List<RemovePingInfo>();
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
                _monitorPingInfos = AddMonitorPingInfos(initObj.MonitorIPs, currentMonitorPingInfos);
                _netConnectCollection.NetConnects = _connectFactory.GetNetConnectList(_monitorPingInfos, _pingParams);
                _logger.Debug("MonitorPingInfos : " + JsonUtils.writeJsonObjectToString(_monitorPingInfos));
                _logger.Debug("MonitorIPs : " + JsonUtils.writeJsonObjectToString(initObj.MonitorIPs));
                _logger.Debug("PingParams : " + JsonUtils.writeJsonObjectToString(_pingParams));
                PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, _monitorPingInfos, _removeMonitorPingInfoIDs, null, _swapMonitorPingInfos, _appID, _piIDKey, false);
            }
            catch (Exception e)
            {
                _logger.Fatal("Error : Unable to init Processor : Error was : " + e.ToString());
            }
            finally
            {
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, true);
            }
        }
        //This method ProcessesMonitorReturnData receives an input object processorDataObj and updates class level variables _removeMonitorPingInfoIDs, _swapMonitorPingInfos, and _removePingInfos based on the data in processorDataObj. It removes items from _removeMonitorPingInfoIDs and _swapMonitorPingInfos and adds items to _removePingInfos.
        public void ProcessesMonitorReturnData(ProcessorDataObj processorDataObj)
        {
            if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
            if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
            if (_removePingInfos == null) _removePingInfos = new List<RemovePingInfo>();
            _removePingInfos.AddRange(processorDataObj.RemovePingInfos);
            processorDataObj.RemoveMonitorPingInfoIDs.ForEach(f =>
            {
                _removeMonitorPingInfoIDs.Remove(f);
            });
            if (processorDataObj.SwapMonitorPingInfos != null) processorDataObj.SwapMonitorPingInfos.ForEach(f =>
            {
                _swapMonitorPingInfos.Remove(f);
            });
        }
        //This method removePublishedPingInfos removes PingInfos from _monitorPingInfos based on the _removePingInfos list. The method returns a ResultObj with a success flag and message indicating the number of removed PingInfos.
        private ResultObj removePublishedPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            if (_removePingInfos == null || _removePingInfos.Count() == 0 || _monitorPingInfos == null || _monitorPingInfos.Count() == 0)
            {
                result.Success = false;
                result.Message = " No PingInfos removed. ";
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
            result.Success = true;
            result.Message = " Removed " + count + " PingInfos from MonitorPingInfos. ";
            return result;
        }
        //This is a method that adds MonitorPingInfos to a list of monitor IPs. If the MonitorPingInfo for a given monitor IP already exists, it updates it. Otherwise, it creates a new MonitorPingInfo object and fills it with data. The method returns a list of the newly added or updated MonitorPingInfos.
        private List<MonitorPingInfo> AddMonitorPingInfos(List<MonitorIP> monitorIPs, List<MonitorPingInfo> currentMonitorPingInfos)
        {
            var monitorPingInfos = new List<MonitorPingInfo>();
            int i = 0;
            foreach (MonitorIP monIP in monitorIPs)
            {
                MonitorPingInfo monitorPingInfo = currentMonitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);
                if (monitorPingInfo != null)
                {
                    _logger.Debug("Updatating MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    //monitorPingInfo.MonitorStatus.MonitorPingInfo = null;
                    //monitorPingInfo.MonitorStatus.MonitorPingInfoID = 0;
                }
                else
                {
                    monitorPingInfo = new MonitorPingInfo();
                    monitorPingInfo.MonitorIPID = monIP.ID;
                    _logger.Debug("Adding new MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    monitorPingInfo.ID = monIP.ID;
                    monitorPingInfo.UserID = monIP.UserID;
                }
                fillPingInfo(monitorPingInfo, monIP);
                monitorPingInfos.Add(monitorPingInfo);
                i++;
            }
            return monitorPingInfos;
        }
        //The method fillPingInfo populates the MonitorPingInfo object with values from the MonitorIP object. The MonitorPingInfo object properties are assigned the values of the corresponding properties of the MonitorIP object, except for Timeout property. If Timeout property of MonitorIP is 0, it will be assigned with the default value of _pingParams.Timeout.
        private void fillPingInfo(MonitorPingInfo monitorPingInfo, MonitorIP monIP)
        {
            monitorPingInfo.ID = monIP.ID;
            monitorPingInfo.AppID = _appID;
            monitorPingInfo.Address = monIP.Address;
            monitorPingInfo.Port = monIP.Port;
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
        // /This method GetNetConnect returns a Task object for a network connection with the given monitorPingInfoID. It searches the list of _netConnects for an object with the matching ID and returns the connect task from that object. If no match is found, a completed task is returned.
        /*private Task GetNetConnect(int monitorPingInfoID)
        {
            var connectTask = _netConnects.FirstOrDefault(w => w.MonitorPingInfo.ID == monitorPingInfoID);
            // return completed task if no netConnect found
            if (connectTask == null) return Task.FromResult<object>(null);
            return connectTask.connect();
        }*/

        private async Task HandleLongRunningTask(NetConnect netConnect)
        {
            if (_longRunningTaskIDs.Contains(netConnect.MonitorPingInfo.MonitorIPID)){
                _logger.Warn($" Warning: The Quantum task for MonitorPingInfoID {netConnect.MonitorPingInfo.MonitorIPID} is already running.");
                return;
            }
             if (_quantumTaskQueueIDs.Contains(netConnect.MonitorPingInfo.MonitorIPID)){
                _logger.Warn($" Warning: Rejecting Quantum task for MonitorPingInfoID {netConnect.MonitorPingInfo.MonitorIPID} is already in queue" );
                return;
            }
            // Increment waiting tasks counter
            Interlocked.Increment(ref _waitingTasksCounter);
            _quantumTaskQueueIDs.Add(netConnect.MonitorPingInfo.MonitorIPID);
            // Check if the waitingTaskCounter exceeds the threshold
            if (_waitingTasksCounter > _maxTaskQueueSize)
            {
                _logger.Error($" Error: The waitingTaskCounter has reached {_waitingTasksCounter}, which exceeds the limit of {_maxTaskQueueSize}.");
                // You can handle this situation here or log additional information if needed
            }

            //_logger.Fatal($" Waiting tasks: {_waitingTasksCounter} . MonitorIPID: {netConnect.MonitorPingInfo.MonitorIPID}");

            // Wait for a semaphore slot
            await _taskSemaphore.WaitAsync();
             _logger.Error($" Starting task count running: {_waitingTasksCounter} . MonitorIPID: {netConnect.MonitorPingInfo.MonitorIPID}");
  

            // Decrement waiting tasks counter
            Interlocked.Decrement(ref _waitingTasksCounter);
            _quantumTaskQueueIDs.Remove(netConnect.MonitorPingInfo.MonitorIPID);
            _longRunningTaskIDs.Add(netConnect.MonitorPingInfo.MonitorIPID);
            var task = netConnect.Connect();


            // Add a continuation to remove the task from the list and release the semaphore when it's complete
            _ = task.ContinueWith((t) =>
            {
                lock (_longRunningTaskIDs)
                {
                    _longRunningTaskIDs.Remove(netConnect.MonitorPingInfo.MonitorIPID);
                       // log output netConnect.MonitorPingInfo.PingInfos write as json
                      _logger.Error($" Finished task for MonitorIPID: {netConnect.MonitorPingInfo.MonitorIPID} . PingInfos: {JsonUtils.writeJsonObjectToString(netConnect.MonitorPingInfo.PingInfos)}");

                }
                _taskSemaphore.Release(); // Release the semaphore slot
            });
        }


        // This method is used to connect to remote hosts by creating and executing NetConnect objects. 
        public async Task<ResultObj> Connect(ProcessorConnectObj connectObj)
        {
            _awake = true;
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
            if (_monitorPingInfos == null || _monitorPingInfos.Where(x => x.Enabled == true).Count() == 0)
            {
                result.Message += " Warning : There is no MonitorPingInfo data. ";
                _logger.Warn(" Warning : There is no MonitorPingInfo data. ");
                result.Success = false;
                _awake = false;
                PublishRepo.ProcessorReady(_logger, _rabbitRepo, _appID, true);
                return result;
            }
            // Time interval between Now and NextRun
            int executionTime = connectObj.NextRunInterval - _pingParams.Timeout - connectObj.MaxBuffer;
            int timeToWait = executionTime / _monitorPingInfos.Where(x => x.Enabled == true).Count();
            if (timeToWait < 25)
            {
                result.Message += " Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ";
                _logger.Warn(" Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ");
            }
            result.Message += " Info : Time to wait : " + timeToWait + "ms. ";
            try
            {
                var pingConnectTasks = new List<Task>();
                result.Message += " MEMINFO Before : " + GC.GetGCMemoryInfo().TotalCommittedBytes + " : ";
                GC.Collect();
                result.Message += " MEMINFO After : " + GC.GetGCMemoryInfo().TotalCommittedBytes + " : ";
                GC.TryStartNoGCRegion(104857600, false);
                var filteredNetConnects = _netConnectCollection.GetFilteredNetConnects().Where(w => w.MonitorPingInfo.Enabled == true).ToList();
                foreach (var netConnect in filteredNetConnects)
                {
                    netConnect.PiID = _piIDKey;
                    _piIDKey++;
                    if (netConnect.IsLongRunning)
                    {
                         _ = HandleLongRunningTask(netConnect); // Call the new method to handle long-running tasks without awaiting it
                        
                    }
                    else
                    {
                        pingConnectTasks.Add(netConnect.Connect());
                    }

                    await Task.Delay(timeToWait); // Use 'await' here
                };
                await Task.Delay(timeToWait).ConfigureAwait(false);
                if (GCSettings.LatencyMode == GCLatencyMode.NoGCRegion)
                    GC.EndNoGCRegion();
                //new System.Threading.ManualResetEvent(false).WaitOne(_pingParams.Timeout);
                result.Message += " Success : Completed all NetConnect tasks in " + timerInner.Elapsed.TotalMilliseconds + " ms ";
                result.Success = true;
            }
            catch (Exception e)
            {
                result.Message += " Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ";
                result.Success = false;
                _logger.Fatal(" Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ");
            }
            finally
            {
                if (_monitorPingInfos.Count > 0)
                {
                    result.Message += removePublishedPingInfos().Message;
                    PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, _monitorPingInfos, _removeMonitorPingInfoIDs, _removePingInfos, _swapMonitorPingInfos, _appID, _piIDKey, true);
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
            //int maxID = _monitorPingInfos.Max(m => m.ID);
            string message = "";
            //Add and update
            foreach (UpdateMonitorIP monIP in monitorIPQueue)
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
                            NetConnect netConnect = _netConnectCollection.NetConnects.FirstOrDefault(w => w.MonitorPingInfo.ID == monitorPingInfo.ID);
                            if (netConnect != null)
                            {
                                int index = _netConnectCollection.NetConnects.IndexOf(netConnect);
                                NetConnect newNetConnect = _connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams);
                                _netConnectCollection.NetConnects[index] = newNetConnect;
                            }
                            else
                            {
                                // recreate if it is missing
                                _netConnectCollection.NetConnects.Add(_connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams));
                            }
                        }
                        else
                        {
                            NetConnect netConnect = _netConnectCollection.NetConnects.FirstOrDefault(w => w.MonitorPingInfo.ID == monitorPingInfo.ID);
                            fillPingInfo(monitorPingInfo, monIP);
                            if (netConnect != null)
                            {
                                netConnect.MonitorPingInfo = monitorPingInfo;
                            }
                            else
                            {
                                // recreate if its missing
                                _netConnectCollection.NetConnects.Add(_connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams));
                            }
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
                        fillPingInfo(monitorPingInfo, monIP);
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
                    _monitorPingInfos.Add(monitorPingInfo);
                    NetConnect netConnect = _connectFactory.GetNetConnectObj(monitorPingInfo, _pingParams);
                    _netConnectCollection.NetConnects.Add(netConnect);
                }
            }
            //Delete
            List<MonitorPingInfo> delList = new List<MonitorPingInfo>();
            foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
            {
                kvp.Value.ForEach(f =>
                    {
                        if (f.Delete)
                        {
                            var del = _monitorPingInfos.Where(w => w.MonitorIPID == f.ID).FirstOrDefault();
                            delList.Add(del);
                            _logger.Info(" Deleting MonitorIP with ID " + f.ID);
                            if (!f.IsSwapping) _removeMonitorPingInfoIDs.Add(del.MonitorIPID);
                        }
                    });
            }
            foreach (MonitorPingInfo del in delList)
            {
                _monitorPingInfos.Remove(del);
            }
            message += " Success : Updated MonitorPingInfos. ";
            // Update statestore with new MonitorIPs
            message += UpdateMonitorIPsInStatestore(monitorIPQueue);
            // reset queue to empty
            _monitorIPQueueDic = new Dictionary<string, List<UpdateMonitorIP>>();
            return message;
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
        private void ProcessMonitorIPDic()
        {
            // Get all MonitorIPs from the queue
        }
        // This method updates the AlertSent property of MonitorPingInfo objects in the _monitorPingInfos list, based on the provided monitorIPIDs list. For each id in monitorIPIDs, it retrieves the corresponding MonitorPingInfo object and sets its AlertSent property to alertSent. The method returns a list of ResultObj objects, where each object represents the result of updating the AlertSent property for a specific MonitorPingInfo object.
        public List<ResultObj> UpdateAlertSent(List<int> monitorIPIDs, bool alertSent)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorIPIDs)
            {
                var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.MonitorIPID == id);
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
        // This method updates the AlertFlag field for multiple MonitorPingInfo objects based on the provided monitorIPIDs. The method returns a list of ResultObj objects indicating the success or failure of the update for each MonitorPingInfo. If the MonitorPingInfo with a given id is found in the _monitorPingInfos collection, the AlertFlag field is updated to the provided alertFlag value, and a success message is added to the ResultObj. If the MonitorPingInfo is not found, a failure message is added to the ResultObj.
        public List<ResultObj> UpdateAlertFlag(List<int> monitorIPIDs, bool alertFlag)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorIPIDs)
            {
                var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.MonitorIPID == id);
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
                var updateMonitorPingInfo = _monitorPingInfos.FirstOrDefault(w => w.MonitorIPID == alertFlagObj.ID && w.AppID == alertFlagObj.AppID);
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
    }
}