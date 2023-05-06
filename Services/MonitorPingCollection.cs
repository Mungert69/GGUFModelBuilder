using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System;
using NetworkMonitor.Objects;
using System.Threading;
using System.Threading.Tasks;
using MetroLog;
namespace NetworkMonitor.Processor.Services
{
    public class MonitorPingCollection
    {
        private readonly ILogger _logger;
        private string _appID;
        private SemaphoreSlim _localLock = new SemaphoreSlim(1);
        private PingParams _pingParams;
        private BlockingCollection<RemovePingInfo> _removePingInfos = new BlockingCollection<RemovePingInfo>();
        private BlockingCollection<MonitorPingInfo> _monitorPingInfos = new BlockingCollection<MonitorPingInfo>();
        public BlockingCollection<MonitorPingInfo> MonitorPingInfos { get => _monitorPingInfos; }
        public BlockingCollection<RemovePingInfo> RemovePingInfos { get => _removePingInfos; set => _removePingInfos = value; }
        public MonitorPingCollection(ILogger logger)
        {
            _logger = logger;
        }
        public void SetVars(string appID, PingParams pingParams)
        {
            _appID = appID;
            _pingParams = pingParams;
        }
        public void Zero(MonitorPingInfo monitorPingInfo)
        {
            monitorPingInfo.DateStarted = DateTime.UtcNow;
            monitorPingInfo.PacketsLost = 0;
            monitorPingInfo.PacketsLostPercentage = 0;
            monitorPingInfo.PacketsRecieved = 0;
            monitorPingInfo.PacketsSent = 0;
            monitorPingInfo.PingInfos = new BlockingCollection<PingInfo>();
            monitorPingInfo.RoundTripTimeAverage = 0;
            monitorPingInfo.RoundTripTimeMaximum = 0;
            monitorPingInfo.RoundTripTimeMinimum = _pingParams.Timeout;
            monitorPingInfo.RoundTripTimeTotal = 0;
        }
        public async Task ZeroMonitorPingInfos(SemaphoreSlim lockObj)
        {
            await lockObj.WaitAsync();
            try
            {
                foreach (MonitorPingInfo monitorPingInfo in _monitorPingInfos)
                {
                    Zero(monitorPingInfo);
                }
            }
            catch (Exception ex)
            {
                _logger.Error(" ZeroMonitorPingInfos " + ex.Message + " " + ex.StackTrace);
            }
            finally
            {
                lockObj.Release();
            }
        }
        public void Merge(MPIConnect mpiConnect, int monitorIPID)
        {

            var mergeMonitorPingInfo = _monitorPingInfos.FirstOrDefault(p => p.MonitorIPID == monitorIPID);
            if (mergeMonitorPingInfo != null)
            {
                mergeMonitorPingInfo.PacketsSent++;
                if (mpiConnect.IsUp)
                {
                    ushort RoundTrip = (ushort)mpiConnect.PingInfo.RoundTripTime;
                    mergeMonitorPingInfo.PacketsRecieved++;
                    mergeMonitorPingInfo.RoundTripTimeTotal += (int)mpiConnect.PingInfo.RoundTripTime;
                    if (mergeMonitorPingInfo.RoundTripTimeMaximum < RoundTrip)
                    {
                        mergeMonitorPingInfo.RoundTripTimeMaximum = RoundTrip;
                    }
                    if (mergeMonitorPingInfo.RoundTripTimeMinimum > RoundTrip)
                    {
                        mergeMonitorPingInfo.RoundTripTimeMinimum = RoundTrip;
                    }
                    mergeMonitorPingInfo.RoundTripTimeAverage = mergeMonitorPingInfo.RoundTripTimeTotal / (float)mergeMonitorPingInfo.PacketsRecieved;
                }
                else
                {
                    mergeMonitorPingInfo.PacketsLost++;
                    mergeMonitorPingInfo.MonitorStatus.DownCount++;
                }
                mergeMonitorPingInfo.PacketsLostPercentage = (float)((double)mergeMonitorPingInfo.PacketsLost / (double)(mergeMonitorPingInfo.PacketsSent) * 100);
                mergeMonitorPingInfo.PingInfos.Add(mpiConnect.PingInfo);
                //mergeMonitorPingInfo.MonitorStatus.AlertFlag = monitorPingInfo.MonitorStatus.AlertFlag;
                //mergeMonitorPingInfo.MonitorStatus.AlertSent = monitorPingInfo.MonitorStatus.AlertSent;
                if (mergeMonitorPingInfo.IsDirtyDownCount)
                {
                    mergeMonitorPingInfo.MonitorStatus.DownCount = 0;
                    mergeMonitorPingInfo.IsDirtyDownCount = false;
                }
                mergeMonitorPingInfo.MonitorStatus.IsUp = mpiConnect.IsUp;
                mergeMonitorPingInfo.MonitorStatus.EventTime = mpiConnect.EventTime;
                mergeMonitorPingInfo.MonitorStatus.Message = mpiConnect.Message;
                mergeMonitorPingInfo.Status = mpiConnect.Message;
            }

        }
        //This method removePublishedPingInfos removes PingInfos from MonitorPingInfos based on the _removePingInfos list. The method returns a ResultObj with a success flag and message indicating the number of removed PingInfos.
        /* public async Task<ResultObj> RemovePublishedPingInfos(SemaphoreSlim lockObj)
         {
             await lockObj.WaitAsync();
             var result = new ResultObj();
             try
             {
                 int count = 0;
                 int failCount = 0;
                 if (_removePingInfos == null || _removePingInfos.Count() == 0 || _monitorPingInfos == null || _monitorPingInfos.Count() == 0)
                 {
                     result.Success = false;
                     result.Message = " No PingInfos removed. ";
                     return result;
                 }
                 foreach (var f in MonitorPingInfos.ToList())
                 {

                     _removePingInfos.Where(w => w.MonitorPingInfoID == f.MonitorIPID).ToList().ForEach(p =>
                          {
                              var r = f.PingInfos.FirstOrDefault(f => f.ID == p.ID);
                              if (f.PingInfos.TryTake(out r)) count++;
                              else failCount++;
                          });
                     _removePingInfos.RemoveAll(r => r.MonitorPingInfoID == f.MonitorIPID);
                 }
                 result.Success = true;
                 result.Message = " Removed " + count + " PingInfos from MonitorPingInfos. Failed to remove " + failCount + " PingInfos.";
             }
             catch (Exception ex)
             {
                 _logger.Error(" RemovePublishedPingInfos " + ex.Message + " " + ex.StackTrace);
             }
             finally
             {
                 lockObj.Release();
             }
             return result;
         }*/


        //This method removePublishedPingInfos removes PingInfos from MonitorPingInfos based on the _removePingInfos list. The method returns a ResultObj with a success flag and message indicating the number of removed PingInfos.
        public ResultObj RemovePublishedPingInfosForID(int monitorIPID)
        {
            var result = new ResultObj();

            int count = 0;
            int failCount = 0;
            try
            {
                var monitorPingInfo = _monitorPingInfos.FirstOrDefault(p => p.MonitorIPID == monitorIPID);

                _removePingInfos.Where(w => w.MonitorPingInfoID == monitorIPID).ToList().ForEach(p =>
                     {
                         var r = monitorPingInfo.PingInfos.FirstOrDefault(f => f.ID == p.ID);
                         if (monitorPingInfo.PingInfos.TryTake(out r)) count++;
                         else failCount++;
                     });
                _removePingInfos.Where(r => r.MonitorPingInfoID == monitorPingInfo.MonitorIPID).ToList().ForEach(p =>
                {
                    _removePingInfos.TryTake(out p);
                });

                result.Success = true;
                result.Message = " Removed " + count + " PingInfos from MonitorPingInfos. Failed to remove " + failCount + " PingInfos.";

            }
            catch (Exception ex)
            {
                _logger.Error(" RemovePublishedPingInfosForID " + ex.Message + " " + ex.StackTrace);
            }





            return result;
        }

        //This is a method that adds MonitorPingInfos to a list of monitor IPs. If the MonitorPingInfo for a given monitor IP already exists, it updates it. Otherwise, it creates a new MonitorPingInfo object and fills it with data. The method returns a list of the newly added or updated MonitorPingInfos.
        public async Task MonitorPingInfoFactory(List<MonitorIP> monitorIPs, List<MonitorPingInfo> currentMonitorPingInfos, SemaphoreSlim lockObj)
        {
            await lockObj.WaitAsync();
            try
            {

                int i = 0;
                while (_monitorPingInfos.TryTake(out _)) { }
                foreach (MonitorIP monIP in monitorIPs)
                {
                    MonitorPingInfo monitorPingInfo = currentMonitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);
                    if (monitorPingInfo != null)
                    {
                        _logger.Debug("Updatating MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    }
                    else
                    {
                        monitorPingInfo = new MonitorPingInfo();
                        _logger.Debug("Adding new MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    }
                    FillPingInfo(monitorPingInfo, monIP);
                    _monitorPingInfos.Add(monitorPingInfo);
                    i++;
                }
            }
            catch (Exception ex)
            {
                _logger.Error("MonitorPingInfoFactory error: " + ex.Message + " " + ex.StackTrace);
            }
            finally
            {
                lockObj.Release();
            }

        }
        public void FillPingInfo(MonitorPingInfo monitorPingInfo, MonitorIP monIP)
        {
            monitorPingInfo.MonitorIPID = monIP.ID;
            monitorPingInfo.UserID = monIP.UserID; ;
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
    }
}