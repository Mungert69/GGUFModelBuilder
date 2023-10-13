using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System;
using NetworkMonitor.Objects;
using NetworkMonitor.Utils;
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
        private ConcurrentDictionary<ulong, RemovePingInfo> _removePingInfos = new ConcurrentDictionary<ulong, RemovePingInfo>();
        private ConcurrentDictionary<int, MonitorPingInfo> _monitorPingInfos = new ConcurrentDictionary<int, MonitorPingInfo>();
        private ConcurrentDictionary<ulong, PingInfo> _pingInfos = new ConcurrentDictionary<ulong, PingInfo>();
        public ConcurrentDictionary<int, MonitorPingInfo> MonitorPingInfos { get => _monitorPingInfos; }
        public ConcurrentDictionary<ulong, RemovePingInfo> RemovePingInfos { get => _removePingInfos; }
        public ConcurrentDictionary<ulong, PingInfo> PingInfos { get => _pingInfos; }
        public MonitorPingCollection(ILogger logger)
        {
            _logger = logger;
        }
        public void SetVars(string appID, PingParams pingParams)
        {
            _appID = appID;
            _pingParams = pingParams;
        }
        private void Zero(MonitorPingInfo monitorPingInfo)
        {
            monitorPingInfo.DateStarted = DateTime.UtcNow;
            monitorPingInfo.PacketsLost = 0;
            monitorPingInfo.PacketsLostPercentage = 0;
            monitorPingInfo.PacketsRecieved = 0;
            monitorPingInfo.PacketsSent = 0;
            bool failFlag = false;

            _pingInfos.Values.Where(w => w.MonitorPingInfoID == monitorPingInfo.MonitorIPID).ToList().ForEach(f =>
            {
                bool success = _pingInfos.TryRemove(f.ID, out _);
                if (!success && !failFlag)
                {
                    failFlag = true;
                }
            });

            if (failFlag)
            {
                _logger.Error(" ZeroMonitorPingInfos failed to Zero PingInfos for MonitorPingInfo.MonitorIPID  " + monitorPingInfo.MonitorIPID);
            }
            //monitorPingInfo.PingInfos = new BlockingCollection<PingInfo>();
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
                foreach (MonitorPingInfo monitorPingInfo in _monitorPingInfos.Values.ToList())
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
            var mergeMonitorPingInfo = _monitorPingInfos.Values.FirstOrDefault(p => p.MonitorIPID == monitorIPID);
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
                    mergeMonitorPingInfo.MonitorStatus.ResetDownCount();
                    mergeMonitorPingInfo.IsDirtyDownCount = false;
                }
                else
                {
                    mergeMonitorPingInfo.PacketsLost++;
                    mergeMonitorPingInfo.MonitorStatus.IncrementDownCount();
                }
                mergeMonitorPingInfo.PacketsLostPercentage = (float)((double)mergeMonitorPingInfo.PacketsLost / (double)(mergeMonitorPingInfo.PacketsSent) * 100);
                PingInfos.TryAdd(mpiConnect.PingInfo.ID, mpiConnect.PingInfo);
                //mergeMonitorPingInfo.MonitorStatus.AlertFlag = monitorPingInfo.MonitorStatus.AlertFlag;
                //mergeMonitorPingInfo.MonitorStatus.AlertSent = monitorPingInfo.MonitorStatus.AlertSent;
                if (mergeMonitorPingInfo.IsDirtyDownCount)
                {
                    mergeMonitorPingInfo.MonitorStatus.ResetDownCount();
                    mergeMonitorPingInfo.IsDirtyDownCount = false;
                }
                mergeMonitorPingInfo.MonitorStatus.IsUp = mpiConnect.IsUp;
                mergeMonitorPingInfo.MonitorStatus.EventTime = mpiConnect.EventTime;
                mergeMonitorPingInfo.MonitorStatus.Message = mpiConnect.Message;
                mergeMonitorPingInfo.Status = mpiConnect.Message;
            }
        }

        // Method to Clear _pingInfos.
        public ResultObj ClearPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            var keysToRemove = _pingInfos.Keys.ToList();

            foreach (var key in keysToRemove)
            {
                if (!_pingInfos.TryRemove(key, out _))
                {
                    failCount++;
                }
                else
                {
                    count++;
                }

            }


            if (failCount == 0 && count > 0)
            {
                result.Success = true;
                result.Message = " Removed " + count + " PingInfos from PingInfos. Failed to remove " + failCount + " PingInfos.";
                return result;
            }
            result.Success = false;
            result.Message = " Failed to remove " + failCount + " PingInfos from PingInfos. Removed " + count + " PingInfos.";
            return result;

        }

        // Clear _monitorPingInfos.
        public ResultObj ClearMonitorPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            // a List of keys from _monitorPingInfos you want to remove
            var keysToRemove = _monitorPingInfos.Keys.ToList();

            foreach (var key in keysToRemove)
            {
                if (!_monitorPingInfos.TryRemove(key, out _))
                {
                    failCount++;
                }
                else
                {
                    count++;
                }

            }



            if (failCount == 0 && count > 0)
            {
                result.Success = true;
                result.Message = " Removed " + count + " MonitorPingInfos from MonitorPingInfos. Failed to remove " + failCount + " MonitorPingInfos.";
                return result;
            }
            if (failCount == 0 && count == 0)
            {
                result.Success = true;
                result.Message = " Nothing removed ";
                return result;
            }
            result.Success = false;
            result.Message = " Failed to remove " + failCount + " MonitorPingInfos from MonitorPingInfos. Removed " + count + " MonitorPingInfos.";
            return result;
        }

        public ResultObj ClearRemovePingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            var keysToRemove = _removePingInfos.Keys.ToList();

            foreach (var key in keysToRemove)
            {
                if (!_removePingInfos.TryRemove(key, out _))
                {
                    failCount++;
                }
                else
                {
                    count++;
                }

            }


            if (failCount == 0 && count > 0)
            {
                result.Success = true;
                result.Message = " Removed " + count + " PingInfos. Failed to remove " + failCount + " PingInfos.";
                return result;
            }
            if (failCount == 0 && count == 0)
            {
                result.Success = true;
                result.Message = " Nothing removed ";
                return result;
            }
            result.Success = false;
            result.Message = " Failed to remove " + failCount + " PingInfos . Removed " + count + " PingInfos.";
            return result;
        }

        public ResultObj RemovePingInfosFromPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            var keysToRemove = _removePingInfos.Keys.ToList();

            foreach (var key in keysToRemove)
            {
                if (!_pingInfos.TryRemove(key, out _))
                {
                    failCount++;
                }
                else
                {
                    count++;
                }

            }
            if (failCount == 0 && count > 0)
            {
                result.Success = true;
                result.Message = " Removed " + count + " PingInfos from RemovePingInfos. ";
                return result;
            }
            if (failCount == 0 && count == 0)
            {
                result.Success = true;
                result.Message = " Nothing removed ";
                return result;
            }
            result.Success = false;
            result.Message = " Failed to remove " + failCount + " PingInfos from RemovePingInfos. Removed " + count + " PingInfos.";
            return result;
        }


        public async Task<ResultObj> RemovePublishedPingInfos(SemaphoreSlim lockObj)
        {
            await lockObj.WaitAsync();
            var result = new ResultObj();
            try
            {
                if (_removePingInfos == null || _removePingInfos.Count() == 0 || _monitorPingInfos == null || _monitorPingInfos.Count() == 0)
                {
                    result.Success = false;
                    result.Message = " No PingInfos removed. ";
                    return result;
                }
                //foreach (var f in MonitorPingInfos.ToList())
                //{
                var resultPingInfos = RemovePingInfosFromPingInfos();
                // if (r != null && PingInfos.TryTake(out r)) count++;
                // else failCount++;

                var resultRemovePingInfos = ClearRemovePingInfos();
                //}
                result.Success = resultPingInfos.Success && resultRemovePingInfos.Success;
                result.Message = resultPingInfos.Message + " " + resultRemovePingInfos.Message;
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
        }
        //This is a method that adds MonitorPingInfos to a list of monitor IPs. If the MonitorPingInfo for a given monitor IP already exists, it updates it. Otherwise, it creates a new MonitorPingInfo object and fills it with data. The method returns a list of the newly added or updated MonitorPingInfos.
        public async Task<ResultObj> MonitorPingInfoFactory(List<MonitorIP> monitorIPs, List<MonitorPingInfo> currentMonitorPingInfos, List<PingInfo> currentPingInfos, SemaphoreSlim lockObj)
        {
            await lockObj.WaitAsync();
            var result = new ResultObj();
            try
            {
                int i = 0;
                var resultRemovePingInfos = ClearMonitorPingInfos();
                var resultPingInfos = ClearPingInfos();
                result.Message = resultPingInfos.Message + " " + resultRemovePingInfos.Message;
                _logger.Info(result.Message);
                foreach (MonitorIP monIP in monitorIPs)
                {
                    MonitorPingInfo monitorPingInfo = currentMonitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);
                    if (monitorPingInfo != null)
                    {
                        _logger.Debug("Updatating MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                        var fillPingInfo = currentPingInfos.Where(w => w.MonitorPingInfoID == monitorPingInfo.MonitorIPID).ToList();
                        foreach (var f in fillPingInfo)
                        {
                            PingInfos.TryAdd(f.ID, f);
                        }
                    }
                    else
                    {
                        monitorPingInfo = new MonitorPingInfo();
                        _logger.Debug("Adding new MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                    }
                    FillPingInfo(monitorPingInfo, monIP);
                    if (!_monitorPingInfos.TryAdd(monitorPingInfo.MonitorIPID, monitorPingInfo))
                    {
                        _logger.Error("MonitorPingInfoFactory failed to add MonitorPingInfo for MonitorIP ID=" + monIP.ID);

                    };
                    i++;
                }
                result.Success = resultPingInfos.Success && resultRemovePingInfos.Success;

                _logger.Info("MonitorPingInfoFactory added " + i + " MonitorPingInfos.");
                _logger.Info("MonitorPingInfoFactory added " + PingInfos.Count() + " PingInfos.");

            }
            catch (Exception ex)
            {
                result.Success = false;
                _logger.Error("MonitorPingInfoFactory error: " + ex.Message + " " + ex.StackTrace);
                result.Message = "MonitorPingInfoFactory error: " + ex.Message + " " + ex.StackTrace;
            }
            finally
            {
                lockObj.Release();
            }
            return result;
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
            monitorPingInfo.Username = monIP.Username;
            monitorPingInfo.Password = monIP.Password;
            monitorPingInfo.AddUserEmail = monIP.AddUserEmail;
            monitorPingInfo.IsEmailVerified = monIP.IsEmailVerified;
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