using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Threading;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.ServiceMessage;
using NetworkMonitor.Objects.Repository;
using MetroLog;

namespace NetworkMonitor.Processor.Services
{
    public class StateSetup
    {
        private ILogger _logger;
        private MonitorPingCollection _monitorPingCollection;
        private SemaphoreSlim _lockObj;
        private IFileRepo _fileRepo;
        List<MonitorPingInfo> _currentMonitorPingInfos;
        List<PingInfo> _currentPingInfos;
        List<MonitorIP> _stateMonitorIPs = new List<MonitorIP>();
        PingParams _statePingParams = new PingParams();

        public List<MonitorPingInfo> CurrentMonitorPingInfos { get => _currentMonitorPingInfos; set => _currentMonitorPingInfos = value; }
        public List<PingInfo> CurrentPingInfos { get => _currentPingInfos; set => _currentPingInfos = value; }

        public StateSetup(ILogger logger, MonitorPingCollection monitorPingCollection, SemaphoreSlim lockObj, IFileRepo fileRepo)
        {
            _logger = logger;
            _fileRepo = fileRepo;
            _monitorPingCollection = monitorPingCollection;
            _lockObj = lockObj;
        }

        public async Task<bool> TotalReset()
        {
            bool initNetConnects = false;
            CurrentMonitorPingInfos = new List<MonitorPingInfo>();
            CurrentPingInfos = new List<PingInfo>();
            _logger.Info(" State Setup : Success : Resetting Processor MonitorPingInfos in statestore");
            var processorDataObj = new ProcessorDataObj()
            {
                MonitorPingInfos = new List<MonitorPingInfo>(),
                RemoveMonitorPingInfoIDs = new List<int>(),
                SwapMonitorPingInfos = new List<SwapMonitorPingInfo>(),
                RemovePingInfos = new List<RemovePingInfo>(),
                PingInfos = new List<PingInfo>(),
                PiIDKey = 1
            };

            try
            {
                await _fileRepo.SaveStateJsonZAsync("ProcessorDataObj", processorDataObj);
                await _fileRepo.SaveStateJsonZAsync<List<MonitorIP>>("MonitorIPs", new List<MonitorIP>());
                await _fileRepo.SaveStateJsonZAsync<PingParams>("PingParams", new PingParams());
                _logger.Info(" State Setup : Success : Reset Processor Objects in statestore ");
                initNetConnects = true;
            }
            catch (Exception e)
            {
                _logger.Error(" State Setup : Error : Could not reset Processor Objects to statestore. Error was : " + e.Message.ToString());
            }

            return initNetConnects;

        }


        public async Task LoadFromState(bool initNetConnects, uint piIDKey, List<int> _removeMonitorPingInfoIDs, List<SwapMonitorPingInfo> _swapMonitorPingInfos, MonitorPingCollection monitorPingCollection)
        {

            initNetConnects = true;
            string infoLog = " Starting Load From State ";
            try
            {
                using (var processorDataObj = await _fileRepo.GetStateStringJsonZAsync<ProcessorDataObj>("ProcessorDataObj"))
                {
                    piIDKey = processorDataObj.PiIDKey;
                    infoLog += " State Setup : Got PiIDKey=" + piIDKey + " . ";
                    CurrentPingInfos = processorDataObj.PingInfos;
                    //_currentMonitorPingInfos = ProcessorDataBuilder.Build(processorDataObj);
                    CurrentMonitorPingInfos = processorDataObj.MonitorPingInfos;
                    _removeMonitorPingInfoIDs = processorDataObj.RemoveMonitorPingInfoIDs;
                    var removePingInfos = processorDataObj.RemovePingInfos.ToList();
                    foreach (var f in removePingInfos)
                    {
                        _monitorPingCollection.RemovePingInfos.TryAdd(f.ID, f);
                    }
                    _swapMonitorPingInfos = processorDataObj.SwapMonitorPingInfos;
                    if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                    if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
                }
                var firstEnabledPingInfo = CurrentMonitorPingInfos.Where(w => w.Enabled == true).FirstOrDefault();

                if (firstEnabledPingInfo != null)
                {
                    infoLog += (" Success : Building MonitorPingInfos from ProcessorDataObj in statestore. First Enabled PingInfo Count = " + CurrentPingInfos.Where(w => w.MonitorPingInfoID == firstEnabledPingInfo.MonitorIPID).Count()) + " ";
                }
                else
                {
                    _logger.Warn(" State Setup : Warning : MonitorPingInfos from ProcessorDataObj in statestore contains no Data .");
                }
            }
            catch (Exception e)
            {
                _logger.Error(" Logged so far : " + infoLog + " : State Setup :Error : Building MonitorPingInfos from ProcessorDataObj in statestore . Error was : " + e.ToString());
                _currentMonitorPingInfos = new List<MonitorPingInfo>();
                _currentPingInfos = new List<PingInfo>();
                if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
            }
            try
            {
                _stateMonitorIPs = await _fileRepo.GetStateJsonZAsync<List<MonitorIP>>("MonitorIPs");
                if (_stateMonitorIPs != null) infoLog += (" Got MonitorIPS from statestore count =" + _stateMonitorIPs.Count()) + " . ";
            }
            catch (Exception e)
            {
                _logger.Warn(" State Setup :Warning : Could get MonitorIPs from statestore. Error was : " + e.Message.ToString());
            }
            try
            {
                _statePingParams = await _fileRepo.GetStateJsonZAsync<PingParams>("PingParams");
                infoLog += (" State Setup :Got PingParams from statestore . ");
            }
            catch (Exception e)
            {
                _logger.Warn(" State Setup :Warning : Could get PingParms from statestore. Error was : " + e.Message.ToString());
            }
            _logger.Info(infoLog);

        }

        public async Task MergeState(ProcessorInitObj initObj)
        {

            if (initObj.MonitorIPs == null || initObj.MonitorIPs.Count == 0)
            {
                _logger.Warn(" State Setup : Warning : There are No MonitorIPs using statestore");
                initObj.MonitorIPs = _stateMonitorIPs;
                if (_stateMonitorIPs == null || _stateMonitorIPs.Count == 0)
                {
                    initObj.MonitorIPs = new List<MonitorIP>();
                    _logger.Error(" State Setup :Error : There are No MonitorIPs in statestore");
                }
            }
            else
            {
                try
                {
                    await _fileRepo.SaveStateJsonZAsync<List<MonitorIP>>("MonitorIPs", initObj.MonitorIPs);
                }
                catch (Exception e)
                {
                    _logger.Error(" State Setup : Error : Unable to Save MonitorIPs to statestore. Error was : " + e.Message);
                }
            }
            if (initObj.PingParams == null)
            {

                if (_statePingParams == null)
                {
                    _logger.Error(" State Setup : Error : There are No PingParams in statestore");
                    throw new ArgumentNullException(" PingParams is null");
                }
                else
                {
                    initObj.PingParams = _statePingParams;
                    _logger.Warn(" State Setup : Warning : There are No PingParams using statestore");
                }
            }
            else
            {

                try
                {
                    await _fileRepo.SaveStateJsonZAsync<PingParams>("PingParams", initObj.PingParams);
                }
                catch (Exception e)
                {
                    _logger.Error(" State Setup : Error : Unable to Save PingParams to statestore. Error was : " + e.Message);
                }
            }



        }
    }
}