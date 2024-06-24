using System;
using System.Collections.Generic;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.Repository;
using NetworkMonitor.Utils;
using NetworkMonitor.Utils.Helpers;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.DTOs;
using System.Linq;
using NetworkMonitor.Connection;
using NetworkMonitor.Objects.Factory;
using System.Threading.Tasks;
using System.Threading;
using System.Runtime;
using System.Diagnostics;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
namespace NetworkMonitor.Processor.Services
{
    public class MonitorPingProcessor : IMonitorPingProcessor
    {
        //private readonly object _lock = new object();
        SemaphoreSlim _lock = new SemaphoreSlim(1);
        //private bool _awake;
        private ILogger _logger;
        //private string _appID = "1";
        private NetConnectConfig _netConfig;
        private LocalProcessorStates _processorStates = new LocalProcessorStates();
        private List<int> _removeMonitorPingInfoIDs = new List<int>();
        private List<SwapMonitorPingInfo> _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
        private NetConnectCollection _netConnectCollection;
        private MonitorPingCollection _monitorPingCollection;
        private IMonitorPingInfoView? _monitoPingInfoView;
        private void SetMonitorPingInfoView()
        {
            if (_monitoPingInfoView != null)
            {
                var monitorPingInfos = new List<MonitorPingInfo>(); ;
                foreach (var monitorPingInfo in _monitorPingCollection.MonitorPingInfos.ToList())
                {
                    monitorPingInfo.Value.PingInfos = new List<PingInfo>();
                    monitorPingInfos.Add(monitorPingInfo.Value);
                }
                _monitoPingInfoView.MonitorPingInfos = monitorPingInfos;
                _monitoPingInfoView.Update();
            }

        }
        private ConcurrentDictionary<string, List<UpdateMonitorIP>> _monitorIPQueueDic = new ConcurrentDictionary<string, List<UpdateMonitorIP>>();
        // private List<MonitorIP> _monitorIPQueue = new List<MonitorIP>();
        //private DaprClient _daprClient;
        private uint _piIDKey = 1;
        private IRabbitRepo _rabbitRepo;
        private IFileRepo _fileRepo;
        //public bool Awake { get => _awake; set => _awake = value; }
        public string AppID { get => _netConfig.AppID; }


        public MonitorPingProcessor(ILogger logger, NetConnectConfig netConfig, IConnectFactory connectFactory, IFileRepo fileRepo, IRabbitRepo rabbitRepo, LocalProcessorStates processorStates, IMonitorPingInfoView? monitorPingInfoView = null)
        {
            _logger = logger;
            _fileRepo = fileRepo;
            _rabbitRepo = rabbitRepo;
            /*_fileRepo.CheckFileExists("ProcessorDataObj", _logger);
            _fileRepo.CheckFileExists("MonitorIPs", _logger);
            _fileRepo.CheckFileExists("PingParams", _logger);*/
            _netConfig = netConfig;
            _netConfig.OnAppIDChangedAsync += HandleAppIDChangedAsync;
            SystemUrl systemUrl = netConfig.LocalSystemUrl;
            _logger.LogInformation(" Starting Processor with AppID = " + AppID + " instanceName=" + systemUrl.RabbitInstanceName + " connecting to RabbitMQ at " + systemUrl.RabbitHostName + ":" + systemUrl.RabbitPort);

            _netConnectCollection = new NetConnectCollection(_logger, _netConfig, connectFactory);
            _monitorPingCollection = new MonitorPingCollection(_logger);
            _monitoPingInfoView = monitorPingInfoView;
            _processorStates = processorStates;
            _processorStates.IsRunning = true;
            _processorStates.RunningMessage = " Success : Agent started ";
        }
        public async Task OnStoppingAsync()
        {
            _logger.LogWarning("PROCESSOR SHUTDOWN : starting shutdown of MonitorPingService");

            try
            {
                _processorStates.IsRunning = false;
                _processorStates.IsSetup = false;
                _processorStates.IsRabbitConnected = false;
                _processorStates.IsConnectRunning = false;
                 _processorStates.SetupMessage = " Agent is shutdown ";
                   _processorStates.RabbitSetupMessage = " Agent is shutdown ";
                     _processorStates.ConnectRunningMessage = " Agent is shutdown ";
                _processorStates.RunningMessage = " Success : Agent shutdown ";
                _logger.LogInformation(" Saving MonitorPingInfos to state");
                await PublishRepo.MonitorPingInfos(_logger, _rabbitRepo, _monitorPingCollection.MonitorPingInfos.Values.ToList(), _removeMonitorPingInfoIDs, new List<RemovePingInfo>(), _swapMonitorPingInfos, _monitorPingCollection.PingInfos.Values.ToList(), _netConfig.AppID, _piIDKey, true, _fileRepo, _netConfig.AuthKey);
                _logger.LogDebug("MonitorPingInfos StateStore : " + JsonUtils.WriteJsonObjectToString(_monitorPingCollection.MonitorPingInfos));
            }
            catch (Exception e)
            {
                _logger.LogError("Error during saving MonitorPingInfos: " + e.ToString());
            }

            try
            {
                _logger.LogInformation(" Sending ProcessorReady = false");
                await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, false);
                _logger.LogInformation(" Success : Published event ProcessorItitObj.IsProcessorReady = false");
            }
            catch (Exception e)
            {
                _logger.LogError("Error during sending ProcessorReady: " + e.ToString());
            }

            try
            {
                await _netConnectCollection.WaitAllTasks();
            }
            catch (Exception e)
            {
                _logger.LogError("Error during waiting for all tasks: " + e.ToString());
            }

            try
            {
                _logger.LogInformation("Shutting down RabbitRepo.");
                _rabbitRepo?.Shutdown();
                _logger.LogInformation(" Success : Shutdown RabbitRepo.");
            }
            catch (Exception e)
            {
                _logger.LogError("Error during shutting down RabbitRepo: " + e.ToString());
            }

            try
            {
                _logger.LogInformation("Shutting down FileRepo.");
                await _fileRepo.ShutdownAsync();
                _logger.LogInformation(" Success : Shutdown FileRepo.");
            }
            catch (Exception e)
            {
                _logger.LogError("Error during shutting down FileRepo: " + e.ToString());
            }

            _logger.LogWarning("PROCESSOR SHUTDOWN : Complete");
        }

        public void Dispose()
        {
            _netConfig.OnAppIDChangedAsync -= HandleAppIDChangedAsync;
        }

        private async Task HandleAppIDChangedAsync(string appID)
        {
            var result = new ResultObj();
            result.Message = " HandleAppIDChange : ";
            result.Success = true;
            List<MonitorIP>? oldMonitorIPs = null;
            try
            {

                oldMonitorIPs = await _fileRepo.GetStateJsonZAsync<List<MonitorIP>>("MonitorIPs");
                if (oldMonitorIPs != null)
                {
                    oldMonitorIPs.ForEach(f => f.AppID = appID);
                    await _fileRepo.SaveStateJsonZAsync<List<MonitorIP>>("MonitorIPs", oldMonitorIPs);
                    result.Message += $" Success : Got MonitorIPS from statestore count ={oldMonitorIPs.Count()}  and Save MonitorIPs back to statestore with new AppID {appID} . ";
                }
            }
            catch (Exception e)
            {
                result.Message += " Error : Could not updated MonitorIPs is state store . Error was : " + e.Message;
                result.Success = false;
            }
            try
            {
                if (oldMonitorIPs == null)
                {
                    result.Message += " MonitorIPs state is empty . Creating empty State . ";
                    oldMonitorIPs = new List<MonitorIP>();
                    await _fileRepo.SaveStateJsonZAsync<List<MonitorIP>>("MonitorIPs", oldMonitorIPs);

                }

            }
            catch (Exception e)
            {
                result.Message += " Error : Could not reset MonitorIPs is state store . Error was : " + e.Message;
                result.Success = false;
            }

            try
            {
                _monitorIPQueueDic = new ConcurrentDictionary<string, List<UpdateMonitorIP>>();
                await _monitorPingCollection.ChangeAppID(_lock, appID);
                result.Message += $" Success : Set all MonitorPingInfo AppIDs to {_netConfig.AppID} ";

            }
            catch (Exception e)
            {
                result.Message += "  Error : Could change MonitorPingInfo AppIDs . Error was : " + e.Message;
                result.Success = false;
            }
            if (result.Success) _logger.LogInformation(result.Message);
            else _logger.LogError(result.Message);

        }

       
        public async Task<ResultObj> SetAuthKey(ProcessorInitObj processorInitObj)
        {
            var result = new ResultObj();
            result.Message = " SetAuthKey : ";
            try
            {
                   _netConfig.AuthKey = processorInitObj.AuthKey;
                _netConfig.AgentUserFlow.IsAuthorized = true;
                _netConfig.AgentUserFlow.IsLoggedInWebsite = false;
                _netConfig.AgentUserFlow.IsHostsAdded = false;
                _fileRepo.CheckFileExists("appsettings.json", _logger);
                string copy = _netConfig.OqsProviderPath;
                _netConfig.OqsProviderPath = _netConfig.OqsProviderPathReadOnly;
                await _fileRepo.SaveStateJsonAsync<NetConnectConfig>("appsettings.json", _netConfig);
                _netConfig.OqsProviderPath = copy;
                result.Message += " Success : Set AuthKey and saved NetConnectConfig to appsettings.json.";
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += $" Error : Could not save NetConnectConfig to appsettings.json . Error was {e.Message}";

            }
            try
            {
                await Init(processorInitObj);
                result.Success = true;
                result.Message += " Success : Ran Processor Init after Setting AuthKey.";
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += $" Error : Could  run Processor Init . Error was {e.Message}";

            }
            return result;

        }
        public async Task<ResultObj> ProcessorUserEvent(ProcessorUserEventObj processorUserEventObj)
        {
            var result = new ResultObj();
            bool isValueChanged = false;
            if (processorUserEventObj.IsLoggedInWebsite != null && _netConfig.AgentUserFlow.IsLoggedInWebsite != (bool)processorUserEventObj.IsLoggedInWebsite)
            {
                _netConfig.AgentUserFlow.IsLoggedInWebsite = (bool)processorUserEventObj.IsLoggedInWebsite;
                result.Success = true;
                result.Message += $" Success : Updated AgentUserFlow.IsLoggedInWebsite to {_netConfig.AgentUserFlow.IsLoggedInWebsite}";
                isValueChanged = true;
            }
            if (processorUserEventObj.IsHostsAdded != null && _netConfig.AgentUserFlow.IsHostsAdded != (bool)processorUserEventObj.IsHostsAdded)
            {
                _netConfig.AgentUserFlow.IsHostsAdded = (bool)processorUserEventObj.IsHostsAdded;
                result.Success = true;
                result.Message += $" Success : Updated AgentUserFlow.IsHostsAdded to {_netConfig.AgentUserFlow.IsHostsAdded}";
                isValueChanged = true;
            }
            if (result.Success == false)
            {
                result.Success = true;
                result.Message += " No ProcessorUserEvent properties set . ";
            }
            if (isValueChanged)
            {
                _fileRepo.CheckFileExists("appsettings.json", _logger);
                await _fileRepo.SaveStateJsonAsync<NetConnectConfig>("appsettings.json", _netConfig);
            }

            return result;
        }
        /*
        The method init(ProcessorInitObj initObj) initializes the state of the program by either resetting the state store or loading the previous state from it. If the initObj.TotalReset flag is set to true, the state store is completely reset, and new empty objects are saved to the state store. If initObj.Reset is set to true, the state of the MonitorPingInfos object is zeroed, and the current state of this object is saved. If neither flag is set, the previous state of the objects is loaded from the state store. The loaded state includes MonitorPingInfos, RemoveMonitorPingInfoIDs, SwapMonitorPingInfos, RemovePingInfos, and PiIDKey. The method uses the FileRepo class to interact with the state store. If any errors occur during the loading or resetting of the state store, an error message is logged.*/
        public async Task<ResultObj> Init(ProcessorInitObj initObj)
        {
            _processorStates.IsSetup = false;
            var result = new ResultObj();
            result.Message += " Init : ";
            result.Success = true;

            var stateSetup = new StateSetup(_logger, _monitorPingCollection, _lock, _fileRepo);
            _removeMonitorPingInfoIDs = new List<int>();
            bool initNetConnects = false;
            bool disableNetConnects = false;
            try
            {
                if (initObj.TotalReset)
                {
                    initNetConnects = await stateSetup.TotalReset();
                    if (!initNetConnects)
                    {
                        result.Message += $" Error : Unable to perform TotalReset exiting Init() .";
                        _logger.LogCritical(result.Message);
                        result.Success = false;
                        _processorStates.IsSetup = result.Success;
                        _processorStates.SetupMessage = result.Message;
                        return result;
                    }
                    disableNetConnects = true;
                }
                else
                {
                    if (initObj.Reset)
                    {

                        _logger.LogInformation("Zeroing MonitorPingInfos for new DataSet");
                        await _monitorPingCollection.ZeroMonitorPingInfos(_lock);
                        stateSetup.CurrentMonitorPingInfos = _monitorPingCollection.MonitorPingInfos.Values.ToList();
                        stateSetup.CurrentPingInfos = _monitorPingCollection.PingInfos.Values.ToList();
                        _piIDKey = 1;
                        initNetConnects = false;
                        disableNetConnects = true;
                    }
                    else
                    {
                        await stateSetup.LoadFromState(initNetConnects, _piIDKey, _removeMonitorPingInfoIDs, _swapMonitorPingInfos, _monitorPingCollection);
                        initNetConnects = false;
                        disableNetConnects = false;
                    }
                }
            }
            catch (Exception e)
            {
                _logger.LogError("Failed : Loading statestore : Error was : " + e.ToString());
                stateSetup.CurrentMonitorPingInfos = new List<MonitorPingInfo>();
                stateSetup.CurrentPingInfos = new List<PingInfo>();
            }
            try
            {
                // Clearing MonitorIP update queue if Total Reset.
                if (initNetConnects) _monitorIPQueueDic = new ConcurrentDictionary<string, List<UpdateMonitorIP>>();
                await stateSetup.MergeState(initObj);
                _logger.LogDebug(" Merge State Complete ");
                if (initObj.PingParams == null)
                {
                    result.Message += $" Critical Error : Can not continue Init. PingParms is null .";
                    _logger.LogCritical(result.Message);
                    result.Success = false;
                    _processorStates.IsSetup = result.Success;
                    _processorStates.SetupMessage = result.Message;
                    return result;

                }
                if (_netConfig.AppID == null)
                {
                    result.Message += $" Critical Error : Can not continue Init. AppID is null .";
                    _logger.LogCritical(result.Message);
                    result.Success = false;
                    _processorStates.IsSetup = result.Success;
                    _processorStates.SetupMessage = result.Message;
                    return result;

                }
                _monitorPingCollection.SetVars(AppID, initObj.PingParams);
                _logger.LogDebug("  MonitorPingCollection Set Vars Complete ");
                await _monitorPingCollection.MonitorPingInfoFactory(initObj.MonitorIPs, stateSetup.CurrentMonitorPingInfos, stateSetup.CurrentPingInfos, _lock);
                _logger.LogDebug(" MonitorPingCollection MonitorPingInfoFactory Complete");
                await _netConnectCollection.NetConnectFactory(_monitorPingCollection.MonitorPingInfos.Values.ToList(), initObj.PingParams, initNetConnects, disableNetConnects, _lock);
                _logger.LogDebug(" NetConnectCollection NetConnectFactory Complete");
                var monitorPingInfos = _monitorPingCollection.MonitorPingInfos.Values.ToList();
                _logger.LogDebug("MonitorPingInfos : " + JsonUtils.WriteJsonObjectToString(monitorPingInfos));
                _logger.LogDebug("MonitorIPs : " + JsonUtils.WriteJsonObjectToString(initObj.MonitorIPs));
                _logger.LogDebug("PingParams : " + JsonUtils.WriteJsonObjectToString(initObj.PingParams));
                await PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, monitorPingInfos, _removeMonitorPingInfoIDs, new List<RemovePingInfo>(), _swapMonitorPingInfos, stateSetup.CurrentPingInfos, _netConfig.AppID, _piIDKey, false, _fileRepo, _netConfig.AuthKey);
            }
            catch (Exception e)
            {
                result.Message += $" Error : Unable to init Processor : Error was : " + e.ToString();
                _logger.LogCritical(result.Message);
                result.Success = false;

            }
            finally
            {
                await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, true);
                //_netConnectCollection.IsLocked = false;
            }
            try
            {
                if (_monitoPingInfoView != null) SetMonitorPingInfoView();
            }
            catch (Exception e)
            {
                result.Success = false;
                _logger.LogError($" Error : Could not set MonitorPingInfoView . Error was : {e.ToString()}");
            }
            _processorStates.IsSetup = result.Success;
            if (result.Success) result.Message += " Success : Setup completed ";
            _processorStates.SetupMessage = result.Message;
            return result;
        }
        // This method is used to connect to remote hosts by creating and executing NetConnect objects. 
        public async Task<ResultObj> Connect(ProcessorConnectObj connectObj)
        {
            var result = new ResultObj();
            if (!_processorStates.IsSetup)
            {
                result.Message += " Warning : Agent not setup. Please wait... ";
                result.Success = false;
                _processorStates.IsConnectRunning = false;
                _processorStates.IsConnectState = ConnectState.Error;
                _processorStates.ConnectRunningMessage = result.Message;
                return result;
            }
            _processorStates.IsConnectRunning = true;
            _processorStates.IsConnectState = ConnectState.Running;
            _processorStates.ConnectRunningMessage = " Success : Monitor running ";
            var timerInner = new Stopwatch();
            timerInner.Start();
            _logger.LogDebug(" ProcessorConnectObj : " + JsonUtils.WriteJsonObjectToString(connectObj));
            await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, false);
 
            result.Success = false;
            result.Message = " SERVICE : MonitorPingProcessor.Connect() ";
            //_logger.LogInformation(" SERVICE : MonitorPingProcessor.Connect() ");
            result.Message += await UpdateMonitorPingInfosFromMonitorIPQueue();
            if (_monitorPingCollection.MonitorPingInfos == null || _monitorPingCollection.MonitorPingInfos.Values.Where(x => x.Enabled == true).Count() == 0)
            {
                result.Message += " Warning : There is no MonitorPingInfo data. ";
                //_logger.LogWarning(" Warning : There is no MonitorPingInfo data. ");
                result.Success = false;
                _processorStates.IsConnectRunning = false;
                _processorStates.IsConnectState = ConnectState.Error;
                _processorStates.ConnectRunningMessage = result.Message;
                await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, true);
                return result;
            }
            try
            {
                //var pingConnectTasks = new List<Task>();
                /*var gcMemoryInfo = GC.GetGCMemoryInfo();
                long totalAvailableMemoryBytes = gcMemoryInfo.TotalAvailableMemoryBytes;
                double totalAvailableMemoryMB = totalAvailableMemoryBytes / (1024.0 * 1024.0);
                _logger.LogInformation($"Info: Total available memory: {totalAvailableMemoryMB:F2} MB");*/
                int countPingInfos = _monitorPingCollection.PingInfos.Count;
                int maxPingInfos = _netConfig.LocalSystemUrl.MaxLoad * _netConfig.LocalSystemUrl.MaxRuntime;
                if (countPingInfos > maxPingInfos)
                {
                    result.Success = false;
                    result.Message += $" Error : The number of stored monitor events ({countPingInfos}) is greater than the maximum threshold ({maxPingInfos}) . Unable to continue monitoring. When the agent connects to the data service it will offload this data and continue. If this message persists then contact support. ";
                    result.Success = false;
                    _processorStates.IsConnectRunning = false;
                    _processorStates.IsConnectState = ConnectState.Error;
                    _processorStates.ConnectRunningMessage = result.Message;
                    try
                    {
                        await PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, _monitorPingCollection.MonitorPingInfos.Values.ToList(), _removeMonitorPingInfoIDs, _monitorPingCollection.RemovePingInfos.Values.ToList(), _swapMonitorPingInfos, _monitorPingCollection.PingInfos.Values.ToList(), _netConfig.AppID, _piIDKey, true, _fileRepo, _netConfig.AuthKey);
                        await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, true);
                    }
                    catch (Exception e)
                    {
                        _logger.LogError($" Error : unable to publish rabbit messages after the maximum monitor events stored threshold was reached. Error was : {e.Message}");
                    }

                    return result;
                }
                /*
#if !ANDROID
                try
                {
                    var message = "";
                    long memoryBeforeGCBytes = GC.GetGCMemoryInfo().TotalCommittedBytes;
                    double memoryBeforeGCMb = (double)memoryBeforeGCBytes / (1024 * 1024);
                    message += $" Info : Memory used Before GC: {memoryBeforeGCMb:F2} MB : ";

                    GC.Collect();

                    long memoryAfterGCBytes = GC.GetGCMemoryInfo().TotalCommittedBytes;
                    double memoryAfterGCMb = (double)memoryAfterGCBytes / (1024 * 1024);
                    message += $" Memory used After GC: {memoryAfterGCMb:F2} MB : ";

                    long noGCRegionSizeBytes = 256 * 1024 * 1024; // 256 MB
                    bool succeeded = GC.TryStartNoGCRegion(noGCRegionSizeBytes, true);


                    if (!succeeded)
                    {
                        _logger.LogWarning(" Warning: Unable to collect garbage or start No GC region.");
                    }
                    result.Message += message;
                }
                catch (Exception ex)
                {
                    _logger.LogError($"Error: {ex.Message}");
                }

#endif
                */

                List<INetConnect> filteredNetConnects = _netConnectCollection.GetFilteredNetConnects().ToList();
                // Time interval between Now and NextRun
                int count = filteredNetConnects.Count();
                if (count == 0)
                {
                    result.Message += " Warning : There are no NetConnects to process. ";
                    _logger.LogWarning(" Warning : There are no NetConnects to process. ");
                    count = 1;

                }
                int executionTime = connectObj.NextRunInterval - connectObj.MaxBuffer;
                int timeToWait = executionTime / count;
                if (timeToWait < 25)
                {
                    result.Message += " Warning : Time to wait between monitor events is less than 25ms.  This may cause problems with the agent.  Reduce the number of hosts monitored. ";
                    //_logger.LogWarning(" Warning : Time to wait is less than 25ms.  This may cause problems with the service.  Please check the schedule settings. ");
                }
                result.Message += " Info : Time to wait between monitor events : " + timeToWait + "ms. ";
                int countDown = filteredNetConnects.Count();
                foreach (var netConnect in filteredNetConnects)
                {
                    netConnect.Cts = new CancellationTokenSource();
                    netConnect.PiID = _piIDKey;
                    _piIDKey++;
                    if (netConnect.IsLongRunning)
                    {
                        // Note we dont set a CancellationTokenSource here as it will be set when the task enters the semaphore
                        _ = _netConnectCollection.HandleLongRunningTask(netConnect, _monitorPingCollection.Merge); // Call the new method to handle long-running tasks without awaiting it
                    }
                    else
                    {
                        // Set timeout via CancellationTokenSource
                        _ = _netConnectCollection.HandleShortRunningTask(netConnect, _monitorPingCollection.Merge); // Call the new method to handle short-running tasks without awaiting it
                    }
                    await Task.Delay(timeToWait);
                    // recalculate the timeToWait based on the timmerInner.Elapsed and countDown
                    if (countDown < 1) countDown = 1;
                    timeToWait = (executionTime - (int)timerInner.ElapsedMilliseconds) / countDown;
                    if (timeToWait < 0)
                    {
                        timeToWait = 0;
                        result.Message += " Warning : Time to wait is less than 0ms.  This may cause problems with the service.  Please check the schedule settings. ";
                    }
                    countDown--;
                };
                /*
#if !ANDROID
                try
                {
                    if (GCSettings.LatencyMode == GCLatencyMode.NoGCRegion)
                    {
                        GC.EndNoGCRegion();
                        _logger.LogInformation("No GC Region ended successfully.");
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogWarning($"Warning: Unable to end No GC Region - {ex.Message}");
                }

#endif
                */

                //new System.Threading.ManualResetEvent(false).WaitOne(_pingParams.Timeout);
                result.Message += " Success : Completed all connections in " + timerInner.Elapsed.TotalMilliseconds + " ms ";
                result.Success = true;
                // Check _netConnectCollection for any NetConnects that have RunningTime > _maxRunningTime and log them.
                result.Message += _netConnectCollection.LogInfo(filteredNetConnects);
            }
            catch (Exception e)
            {
                result.Message += " Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ";
                result.Success = false;
                _logger.LogCritical(" Error : MonitorPingProcessor.Connect Failed : Error Was : " + e.ToString() + " . ");
            }
            finally
            {
                if (_monitorPingCollection.MonitorPingInfos.Count > 0)
                {
                    var removeResult = await _monitorPingCollection.RemovePublishedPingInfos(_lock);
                    result.Message += removeResult.Message;
                    await PublishRepo.MonitorPingInfosLowPriorityThread(_logger, _rabbitRepo, _monitorPingCollection.MonitorPingInfos.Values.ToList(), _removeMonitorPingInfoIDs, _monitorPingCollection.RemovePingInfos.Values.ToList(), _swapMonitorPingInfos, _monitorPingCollection.PingInfos.Values.ToList(), _netConfig.AppID, _piIDKey, true, _fileRepo, _netConfig.AuthKey);

                }
                await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, true);
            }
            int timeTakenInnerInt = (int)timerInner.Elapsed.TotalMilliseconds;
            if (timeTakenInnerInt > connectObj.NextRunInterval)
            {
                result.Message += " Warning : Time to execute the monitor tasks was greater than next schedule time. One schedule will be missed.";
                //_logger.LogWarning(" Warning : Time to execute greater than next schedule time. ");
            }


            try
            {
                if (_monitoPingInfoView != null) SetMonitorPingInfoView();

            }
            catch (Exception e)
            {
                result.Message += $" Error : Could not set UI data view . Error was : {e.Message}";
                result.Success = false;
                _logger.LogError($" Error : Could not set MonitorPingInfoView . Error was : {e.ToString()}");
            }
            if (result.Success)
            {
                result.Message += " Success : All monitor tasks executed in " + timerInner.Elapsed.TotalMilliseconds + " ms ";

                _processorStates.IsConnectState = ConnectState.Waiting;
            }
            else
            {
                result.Message += " All monitor tasks executed in " + timerInner.Elapsed.TotalMilliseconds + " ms with Errors .";
                _processorStates.IsConnectState = ConnectState.Error;
            }
            _processorStates.IsConnectRunning = false;
            _processorStates.ConnectRunningMessage = result.Message;

            return result;
        }
        //This method updates the MonitorPingInfo list with new information from the UpdateMonitorIP queue. The queue is processed and any new or updated information is added to the MonitorPingInfo list and a corresponding NetConnect object is created or updated in the _netConnects list. Deleted items are removed from the MonitorPingInfo list. This method uses the _logger to log information about the updates.
        private async Task<string> UpdateMonitorPingInfosFromMonitorIPQueue()
        {
            // lock the rest of the method
            await _lock.WaitAsync();
            string message = "";
            try
            {
                var monitorIPQueue = new List<UpdateMonitorIP>();
                if (_monitorIPQueueDic.Count() == 0) return " No host config changes to Process . ";
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
                //List<UpdateMonitorIP> addBackMonitorIPs = new List<UpdateMonitorIP>();
                //Add and update
                foreach (UpdateMonitorIP monIP in monitorIPQueue)
                {
                    var monitorPingInfo = _monitorPingCollection.MonitorPingInfos.Values.FirstOrDefault(m => m.MonitorIPID == monIP.ID);
                    // If monitorIP is contained in the list of monitorPingInfos then update it.
                    if (monitorPingInfo != null)
                    {
                        try
                        {
                            bool flag = false;
                            if (monitorPingInfo.EndPointType != monIP.EndPointType) flag = true;
                            _monitorPingCollection.FillPingInfo(monitorPingInfo, monIP);
                            if (flag)
                                message += _netConnectCollection.RemoveAndAdd(monitorPingInfo);
                            else
                                _netConnectCollection.UpdateOrAdd(monitorPingInfo);
                        }
                        catch
                        {
                            message += "Error : Failed to update Host list check Values .";
                        }
                        _logger.LogInformation(" Updating MonitorPingInfo with ID " + monitorPingInfo.ID);
                    }
                    // Else create a new MonitorPingInfo or copy from Queue
                    else
                    {
                        if (!monIP.IsSwapping || monIP.MonitorPingInfo == null)
                        {
                            monitorPingInfo = new MonitorPingInfo();
                            _monitorPingCollection.FillPingInfo(monitorPingInfo, monIP);
                            _logger.LogInformation(" Just adding a new MonitorPingInfo with ID " + monitorPingInfo.ID);
                        }
                        else
                        {
                            monitorPingInfo = monIP.MonitorPingInfo;
                            monitorPingInfo.AppID = _netConfig.AppID;
                            _swapMonitorPingInfos.Add(new SwapMonitorPingInfo()
                            {
                                ID = monitorPingInfo.MonitorIPID,
                                AppID = _netConfig.AppID
                            });
                            _logger.LogInformation(" Adding SwapMonitorPingInfo with ID " + monitorPingInfo.ID + " AppID " + _netConfig.AppID);
                        }
                        if (!_monitorPingCollection.MonitorPingInfos.TryAdd(monitorPingInfo.MonitorIPID, monitorPingInfo))
                        {
                            _logger.LogError(" Error : Failed to add MonitorPingInfo with ID " + monitorPingInfo.ID + " to MonitorPingCollection. ");
                            message += " Error : Failed to add MonitorPingInfo with ID " + monitorPingInfo.ID + " to MonitorPingCollection. ";
                        };
                        _netConnectCollection.Add(monitorPingInfo);
                    }
                }
                //Delete
                List<MonitorPingInfo> delList = new List<MonitorPingInfo>();
                foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
                {
                    kvp.Value.ForEach(f =>
                        {
                            // Skip if monitorIP is in addBackMonitorIPs ie NetConnect still running
                            //if (!addBackMonitorIPs.Contains(f) && f.Delete)
                            if (f.Delete)
                            {
                                var del = _monitorPingCollection.MonitorPingInfos.Where(w => w.Key == f.ID).FirstOrDefault();
                                if (del.Value != null)
                                {
                                    delList.Add(del.Value);
                                    _logger.LogInformation(" Deleting MonitorPingInfo with MonitorIPID " + f.ID);

                                    if (!f.IsSwapping)
                                    {
                                        _removeMonitorPingInfoIDs.Add(del.Value.MonitorIPID);
                                        _logger.LogInformation(" This Not a swap so adding to removeMonitorPingInfosIDS for MonitorPingInfo with MonitorIPID " + f.ID);
                                    }
                                    else
                                        _logger.LogInformation(" This is a swap so not adding to removeMonitorPingInfosIDS for MonitorPingInfo with MonitorIPID " + f.ID);

                                }
                            }
                        });
                }
                var failRemove = new List<int>();
                foreach (MonitorPingInfo del in delList)
                {
                    if (!_monitorPingCollection.MonitorPingInfos.TryRemove(del.MonitorIPID, out _))
                    {
                        failRemove.Add(del.ID);
                        message += " Error : Failed to remove MonitorPingInfo with ID " + del.MonitorIPID + " . ";
                        _logger.LogError(" Error : Failed to remove MonitorPingInfo with ID " + del.MonitorIPID + " . ");
                    }
                    _netConnectCollection.DisableAll(del.MonitorIPID);
                }
                message += " Success : Updated MonitorPingInfos. ";
                // Update statestore with new MonitorIPs
                // remove addBackMonitorIPs from monitorIPQueue
                //monitorIPQueue.RemoveAll(addBackMonitorIPs.Contains);
                var resultStateUpdated = await UpdateMonitorIPsInStatestore(monitorIPQueue);
                message += resultStateUpdated.Message;
                if (resultStateUpdated.Success)
                {
                    // remove all items from queue that are not in failRemove List.
                    foreach (KeyValuePair<string, List<UpdateMonitorIP>> kvp in _monitorIPQueueDic)
                    {
                        kvp.Value.RemoveAll(r => !failRemove.Contains(r.ID));
                    }
                    // remove all empty keys from _monitorIPQueueDic
                    foreach (var key in _monitorIPQueueDic.Keys.ToList())
                    {
                        if (_monitorIPQueueDic.TryGetValue(key, out var value) && value.Count == 0)
                        {
                            _monitorIPQueueDic.TryRemove(key, out _);
                        }
                    }  //_monitorIPQueueDic.Clear();
                }

            }
            catch (Exception e)
            {
                message += " Error : Failed to Process Monitor IP Queue. Error was : " + e.Message.ToString() + " . ";
                _logger.LogError(" Error : Failed to Process Monitor IP Queue. Error was : " + e.ToString() + " . ");
            }
            finally
            {
                _lock.Release();
            }
            return message;
        }
        public void ProcessesMonitorReturnData(ProcessorDataObj processorDataObj)
        {
            if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
            if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();

            try
            {
                processorDataObj.RemovePingInfos.ForEach(f =>
                    {
                        _monitorPingCollection.RemovePingInfos.TryAdd(f.ID, f);
                    });
            }
            catch { }
            try
            {
                _removeMonitorPingInfoIDs = _removeMonitorPingInfoIDs.Except(processorDataObj.RemoveMonitorPingInfoIDs).ToList();

            }
            catch { }
            try
            {
                _swapMonitorPingInfos = _swapMonitorPingInfos.Except(processorDataObj.SwapMonitorPingInfos).ToList();

            }
            catch { }




        }
        private async Task<ResultObj> UpdateMonitorIPsInStatestore(List<UpdateMonitorIP> updateMonitorIPs)
        {
            var result = new ResultObj();
            result.Message = "";
            try
            {
                var stateMonitorIPs = await _fileRepo.GetStateJsonZAsync<List<MonitorIP>>("MonitorIPs");
                if (stateMonitorIPs == null) stateMonitorIPs = new List<MonitorIP>();
                foreach (var updateMonitorIP in updateMonitorIPs)
                {
                    //updateMonitorIP.MonitorPingInfo=null;
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
                await _fileRepo.SaveStateJsonZAsync<List<MonitorIP>>("MonitorIPs", stateMonitorIPs);
                result.Message += " Success : saved MonitorIP queue into statestore. ";
                result.Success = true;
            }
            catch (Exception e)
            {
                result.Message = "Error : Failed to update MonitorIP queue to statestore. Error was : " + e.Message;
                _logger.LogError("Error : Failed to update MonitorIP queue to statestore. Error was : " + e.Message.ToString());
                result.Success = false;
            }
            return result;
        }
        //This method "UpdateMonitorPingInfosFromMonitorIPQueue()" updates the information in the "MonitorPingInfo" class from a queue of updates stored in "_monitorIPQueueDic". 
        public ResultObj AddMonitorIPsToQueueDic(ProcessorQueueDicObj queueDicObj)
        {
            var result = new ResultObj();
            result.Message = " AddMonitorIPsToQueueDic : ";
            // Nothing to process so just return
            if (queueDicObj.MonitorIPs == null || queueDicObj.MonitorIPs.Count == 0)
            {
                result.Success = true;
                result.Message += " Nothing to do : No Data .";
                return result;
            }
            bool flagFailed = false;
            // replace any existing monitorIPs with the monitorIps in the queueDicObj if they exist in _monitorIPQueueDic. Dont replace any monitorIPs that have Delete = true.
            if (_monitorIPQueueDic.ContainsKey(queueDicObj.UserId))
            {
                var existingMonitorIPs = _monitorIPQueueDic[queueDicObj.UserId];
                var newMonitorIPs = queueDicObj.MonitorIPs;
                foreach (var newMonitorIP in newMonitorIPs)
                {
                    var existingMonitorIP = existingMonitorIPs.Where(w => w.ID == newMonitorIP.ID).FirstOrDefault();
                    if (existingMonitorIP != null)
                    {
                        if (!existingMonitorIP.Delete)
                        {
                            existingMonitorIPs.Remove(existingMonitorIP);
                            existingMonitorIPs.Add(newMonitorIP);
                        }
                    }
                    else
                    {
                        existingMonitorIPs.Add(newMonitorIP);
                    }
                }
            }
            else
            {
                // Add to _monitorIPQueueDic
                if (!_monitorIPQueueDic.TryAdd(queueDicObj.UserId, queueDicObj.MonitorIPs)) flagFailed = true;
            }
            if (flagFailed)
            {
                result.Message += " Error : Failed to add MonitorIPs to _monitorIPQueueDic. for user " + queueDicObj.UserId + " .";
                result.Success = false;
                return result;
            }

            result.Success = true;
            result.Message += $" Success : Added {queueDicObj.MonitorIPs.Count} MonitorIPs Queue . ";
            return result;
            //_monitorIPQueueDic.Remove(queueDicObj.UserId);
            //_monitorIPQueueDic.Add(queueDicObj.UserId, queueDicObj.MonitorIPs);
        }
        // This method updates the AlertSent property of MonitorPingInfo objects in the MonitorPingInfos list, based on the provided monitorIPIDs list. For each id in monitorIPIDs, it retrieves the corresponding MonitorPingInfo object and sets its AlertSent property to alertSent. The method returns a list of ResultObj objects, where each object represents the result of updating the AlertSent property for a specific MonitorPingInfo object.
        public List<ResultObj> UpdateAlertSent(List<int> monitorIPIDs, bool alertSent)
        {
            var results = new List<ResultObj>();
            foreach (int id in monitorIPIDs)
            {
                var updateMonitorPingInfo = _monitorPingCollection.MonitorPingInfos.Values.FirstOrDefault(w => w.MonitorIPID == id);
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
                var updateMonitorPingInfo = _monitorPingCollection.MonitorPingInfos.Values.FirstOrDefault(w => w.MonitorIPID == id);
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
        public async Task<List<ResultObj>> ResetAlerts(List<int> monitorIPIDs)
        {
            var results = new List<ResultObj>();
            ResultObj result;
            var alertFlagObjs = new List<AlertFlagObj>();
            monitorIPIDs.ForEach(m =>
            {
                result = new ResultObj();
                var alertFlagObj = new AlertFlagObj();
                alertFlagObj.ID = m;
                alertFlagObj.AppID = AppID;
                alertFlagObjs.Add(alertFlagObj);
                var updateMonitorPingInfo = _monitorPingCollection.MonitorPingInfos.Values.FirstOrDefault(w => w.MonitorIPID == alertFlagObj.ID && w.AppID == alertFlagObj.AppID);
                if (updateMonitorPingInfo == null)
                {
                    result.Success = false;
                    result.Message += " Warning : Unable to find MonitorPingInfo with MonitorIPID " + alertFlagObj.ID + " with AppID " + alertFlagObj.AppID + " . ";
                }
                else
                {
                    updateMonitorPingInfo.MonitorStatus.AlertFlag = false;
                    updateMonitorPingInfo.MonitorStatus.AlertSent = false;
                    updateMonitorPingInfo.IsDirtyDownCount = true;
                    updateMonitorPingInfo.MonitorStatus.ResetDownCount();
                    result.Success = true;
                    result.Message += " Success : updated MonitorPingInfo with MonitorIPID " + alertFlagObj.ID + " with AppID " + alertFlagObj.AppID + " . ";
                }
                results.Add(result);
            });
            results.Add(await PublishRepo.AlertMessgeResetAlerts(_rabbitRepo, alertFlagObjs, _netConfig.AppID, _netConfig.AuthKey));
            return results;
        }
        public async Task<ResultObj> WakeUp()
        {
           
            ResultObj result = new ResultObj();
            result.Message = "SERVICE : MonitorPingProcessor.WakeUp() ";
            try
            {
                if (!_processorStates.IsSetup) {
                    result.Message += " Warning : Received WakeUp but setup is running. ";
                    result.Success = false;
                    return result;
                }
                if (_processorStates.IsConnectRunning)
                {
                    result.Message += " Warning : Received WakeUp but processor is currently running";
                    result.Success = false;
                }
                else
                {
                    await PublishRepo.ProcessorReady(_logger, _rabbitRepo, _netConfig.AppID, true);
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
        /* public async Task WaitInit(ProcessorInitObj initObj)
         {
             _netConnectCollection.IsLocked = true;
             while (_awake)
             {
                 await Task.Delay(1000);
             }
             Init(initObj);
         }*/
    }
}