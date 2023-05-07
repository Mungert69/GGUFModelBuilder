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
        private RetryBlockingCollection<RemovePingInfo> _removePingInfos = new RetryBlockingCollection<RemovePingInfo>();
        private RetryBlockingCollection<MonitorPingInfo> _monitorPingInfos = new RetryBlockingCollection<MonitorPingInfo>();
        private RetryBlockingCollection<PingInfo> _pingInfos = new RetryBlockingCollection<PingInfo>();
        public BlockingCollection<MonitorPingInfo> MonitorPingInfos { get => _monitorPingInfos; }
        public BlockingCollection<RemovePingInfo> RemovePingInfos { get => _removePingInfos; }
        public BlockingCollection<PingInfo> PingInfos { get => _pingInfos; }
        public MonitorPingCollection(ILogger logger)
        {
            _logger = logger;
        }
        public void SetVars(string appID, PingParams pingParams)
        {
            _appID = appID;
            _pingParams = pingParams;
        }
        private async Task Zero(MonitorPingInfo monitorPingInfo)
        {
            monitorPingInfo.DateStarted = DateTime.UtcNow;
            monitorPingInfo.PacketsLost = 0;
            monitorPingInfo.PacketsLostPercentage = 0;
            monitorPingInfo.PacketsRecieved = 0;
            monitorPingInfo.PacketsSent = 0;
            bool failFlag = false;
            _pingInfos.Where(w => w.MonitorPingInfoID == monitorPingInfo.MonitorIPID).ToList().ForEach(async f =>
            {
                var (success, item) = await _pingInfos.TryTakeWithRetryAsync(f);
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
                foreach (MonitorPingInfo monitorPingInfo in _monitorPingInfos)
                {
                    await Zero(monitorPingInfo);
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
                PingInfos.Add(mpiConnect.PingInfo);
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

        // Method to Clear _pingInfos.
        public async Task<ResultObj> ClearPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            await Task.Run(() =>
            {
                _pingInfos.ToList().ForEach(async p =>
                            {
                                var (success, item) = await _pingInfos.TryTakeWithRetryAsync(p);
                                if (success) count++;
                                else failCount++;
                            });
            });

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
        public async Task<ResultObj> ClearMonitorPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            await Task.Run(() =>
            {
                _monitorPingInfos.ToList().ForEach(async p =>
                            {
                                var (success, item) = await _monitorPingInfos.TryTakeWithRetryAsync(p);
                                if (success) count++;
                                else failCount++;
                            });
            });


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

        public async Task<ResultObj> ClearRemovePingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            await Task.Run(async () =>
            {
                foreach (var p in _removePingInfos)
                {
                    var (success, item) = await _removePingInfos.TryTakeWithRetryAsync(p);
                    if (success) count++;
                    else failCount++;
                }
            });


            if (failCount == 0 && count > 0)
            {
                result.Success = true;
                result.Message = " Removed " + count + " PingInfos from RemovePingInfos. Failed to remove " + failCount + " PingInfos.";
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

        public async Task<ResultObj> RemovePingInfosFromPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            int failCount = 0;
            await Task.Run(() =>
            {
                _removePingInfos.ToList().ForEach(async p =>
                                    {
                                        var r = PingInfos.FirstOrDefault(f => f.ID == p.ID);
                                        if (r != null)
                                        {
                                            var (success, item) = await _pingInfos.TryTakeWithRetryAsync(r);
                                            if (success) count++;
                                            else failCount++;
                                        }

                                    });
            });

            if (failCount == 0 && count > 0)
            {
                result.Success = true;
                result.Message = " Removed " + count + " PingInfos from RemovePingInfos. Failed to remove " + failCount + " PingInfos.";
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
                var resultPingInfos = await RemovePingInfosFromPingInfos();
                // if (r != null && PingInfos.TryTake(out r)) count++;
                // else failCount++;

                var resultRemovePingInfos = await ClearRemovePingInfos();
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
                var resultRemovePingInfos = await ClearMonitorPingInfos();
                var resultPingInfos = await ClearPingInfos();
                result.Message = resultPingInfos.Message + " " + resultRemovePingInfos.Message;
                _logger.Info(result.Message);
                foreach (MonitorIP monIP in monitorIPs)
                {
                    MonitorPingInfo monitorPingInfo = currentMonitorPingInfos.FirstOrDefault(m => m.MonitorIPID == monIP.ID);
                    if (monitorPingInfo != null)
                    {
                        _logger.Debug("Updatating MonitorPingInfo for MonitorIP ID=" + monIP.ID);
                        var fillPingInfo = currentPingInfos.Where(w => w.MonitorPingInfoID == monitorPingInfo.MonitorIPID);
                        fillPingInfo.ToList().ForEach(f => PingInfos.Add(f));
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