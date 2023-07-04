using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
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
        private SemaphoreSlim _lockObj ;
         List<MonitorPingInfo> _currentMonitorPingInfos;
            List<PingInfo> _currentPingInfos;
            List<MonitorIP> _stateMonitorIPs = new List<MonitorIP>();
            PingParams _statePingParams = new PingParams();

        public List<MonitorPingInfo> CurrentMonitorPingInfos { get => _currentMonitorPingInfos; set => _currentMonitorPingInfos = value; }
        public List<PingInfo> CurrentPingInfos { get => _currentPingInfos; set => _currentPingInfos = value; }

        public StateSetup(ILogger logger, MonitorPingCollection monitorPingCollection, SemaphoreSlim lockObj)
        {
            _logger = logger;
            _monitorPingCollection = monitorPingCollection;
            _lockObj = lockObj;
        }

        public  bool TotalReset()
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
                FileRepo.SaveStateJsonZ("ProcessorDataObj", processorDataObj);
                FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", new List<MonitorIP>());
                FileRepo.SaveStateJsonZ<PingParams>("PingParams", new PingParams());
                _logger.Info(" State Setup : Success : Reset Processor Objects in statestore ");
                initNetConnects=true;
            }
            catch (Exception e)
            {
                _logger.Error(" State Setup : Error : Could not reset Processor Objects to statestore. Error was : " + e.Message.ToString());
            }

            return initNetConnects;

        }


        public void  LoadFromState(bool initNetConnects, uint piIDKey, List<int> _removeMonitorPingInfoIDs, List<SwapMonitorPingInfo> _swapMonitorPingInfos, MonitorPingCollection monitorPingCollection)
        {
           
            initNetConnects = true;
            string infoLog = "";
            try
            {
                using (var processorDataObj = FileRepo.GetStateStringJsonZ<ProcessorDataObj>("ProcessorDataObj"))
                {
                    piIDKey = processorDataObj.PiIDKey;
                    infoLog += " State Setup : Got PiIDKey=" + piIDKey + " . ";
                    CurrentPingInfos= processorDataObj.PingInfos;
                    //_currentMonitorPingInfos = ProcessorDataBuilder.Build(processorDataObj);
                    CurrentMonitorPingInfos = processorDataObj.MonitorPingInfos;
                    _removeMonitorPingInfoIDs = processorDataObj.RemoveMonitorPingInfoIDs;
                    processorDataObj.RemovePingInfos.ToList().ForEach(f => _monitorPingCollection.RemovePingInfos.TryAdd(f.ID,f));
                    _swapMonitorPingInfos = processorDataObj.SwapMonitorPingInfos;
                    if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                    if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
                }
                 var firstEnabledPingInfo = CurrentMonitorPingInfos.Where(w => w.Enabled == true).FirstOrDefault();

                if (firstEnabledPingInfo != null)
                {               
                    infoLog += (" Success : Building MonitorPingInfos from ProcessorDataObj in statestore. First Enabled PingInfo Count = " + CurrentPingInfos.Where(w => w.MonitorPingInfoID==firstEnabledPingInfo.MonitorIPID).Count()) + " ";
                }
                else
                {
                    _logger.Warn(" State Setup : Warning : MonitorPingInfos from ProcessorDataObj in statestore contains no Data .");
                }
            }
            catch (Exception e)
            {
                _logger.Error(" State Setup :Error : Building MonitorPingInfos from ProcessorDataObj in statestore . Error was : "+e.ToString());
                _currentMonitorPingInfos = new List<MonitorPingInfo>();
                _currentPingInfos = new List<PingInfo>();
                if (_removeMonitorPingInfoIDs == null) _removeMonitorPingInfoIDs = new List<int>();
                if (_swapMonitorPingInfos == null) _swapMonitorPingInfos = new List<SwapMonitorPingInfo>();
            }
            try
            {
                _stateMonitorIPs = FileRepo.GetStateJsonZ<List<MonitorIP>>("MonitorIPs");
                if (_stateMonitorIPs != null) infoLog += (" Got MonitorIPS from statestore count =" + _stateMonitorIPs.Count()) + " . ";
            }
            catch (Exception e)
            {
                _logger.Warn(" State Setup :Warning : Could get MonitorIPs from statestore. Error was : " + e.Message.ToString());
            }
            try
            {
                _statePingParams = FileRepo.GetStateJsonZ<PingParams>("PingParams");
                infoLog += (" State Setup :Got PingParams from statestore . ");
            }
            catch (Exception e)
            {
                _logger.Warn(" State Setup :Warning : Could get PingParms from statestore. Error was : " + e.Message.ToString());
            }
            _logger.Info(infoLog);

        }

        public void MergeState(ProcessorInitObj initObj, bool isSystemElevatedPrivilege ){

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
                        FileRepo.SaveStateJsonZ<List<MonitorIP>>("MonitorIPs", initObj.MonitorIPs);
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
                    else{
                        initObj.PingParams = _statePingParams;
                          _logger.Warn(" State Setup : Warning : There are No PingParams using statestore");
                    }
                }
                else
                {
                  
                    try
                    {
                        FileRepo.SaveStateJsonZ<PingParams>("PingParams", initObj.PingParams);
                    }
                    catch (Exception e)
                    {
                        _logger.Error(" State Setup : Error : Unable to Save PingParams to statestore. Error was : " + e.Message);
                    }
                }
                if (isSystemElevatedPrivilege)
                {
                    _logger.Info(" State Setup : Ping Payload can be customised.  Program is running under privileged user account or is granted cap_net_raw capability using setcap");
                    if (initObj.PingParams != null) initObj.PingParams.IsAdmin = true;
                }
                else
                {
                    _logger.Warn(" State Setup : Unable to send custom ping payload. Run program under privileged user account or grant cap_net_raw capability using setcap.");
                    if (initObj.PingParams != null) initObj.PingParams.IsAdmin = false;
                }
           
            
        }
    }
}