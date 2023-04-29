using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.ServiceMessage;
using MetroLog;

namespace NetworkMonitor.Processor.Services
{
    public class MonitorPingCollection
    {
        private readonly ILogger _logger;
        private string _appID;
        private PingParams _pingParams;
        private List<RemovePingInfo> _removePingInfos = new List<RemovePingInfo>();

        private BlockingCollection<MonitorPingInfo> _monitorPingInfos = new BlockingCollection<MonitorPingInfo>();
        public BlockingCollection<MonitorPingInfo> MonitorPingInfos { get => _monitorPingInfos; set => _monitorPingInfos = value; }

        public List<RemovePingInfo> RemovePingInfos { get => _removePingInfos; set => _removePingInfos = value; }

        public MonitorPingCollection(ILogger logger)
        {
            _logger = logger;

        }
        public void SetVars(string appID, PingParams pingParams)
        {
            _appID = appID;
            _pingParams = pingParams;
        }



        //This method removePublishedPingInfos removes PingInfos from MonitorPingInfos based on the _removePingInfos list. The method returns a ResultObj with a success flag and message indicating the number of removed PingInfos.
        public ResultObj RemovePublishedPingInfos()
        {
            var result = new ResultObj();
            int count = 0;
            if (_removePingInfos == null || _removePingInfos.Count() == 0 || _monitorPingInfos == null || _monitorPingInfos.Count() == 0)
            {
                result.Success = false;
                result.Message = " No PingInfos removed. ";
                return result;
            }
            foreach (var f in MonitorPingInfos.ToList())
            {
                _removePingInfos.Where(w => w.MonitorPingInfoID == f.ID).ToList().ForEach(p =>
                     {
                         f.PingInfos.RemoveAll(r => r.ID == p.ID);
                         count++;
                     });
                _removePingInfos.RemoveAll(r => r.MonitorPingInfoID == f.ID);
            }
            result.Success = true;
            result.Message = " Removed " + count + " PingInfos from MonitorPingInfos. ";
            return result;
        }


        //This is a method that adds MonitorPingInfos to a list of monitor IPs. If the MonitorPingInfo for a given monitor IP already exists, it updates it. Otherwise, it creates a new MonitorPingInfo object and fills it with data. The method returns a list of the newly added or updated MonitorPingInfos.
        public void MonitorPingInfoFactory(List<MonitorIP> monitorIPs, List<MonitorPingInfo> currentMonitorPingInfos)
        {
            int i = 0;
            _monitorPingInfos = new BlockingCollection<MonitorPingInfo>();
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
                FillPingInfo(monitorPingInfo, monIP);
                _monitorPingInfos.Add(monitorPingInfo);
                i++;
            }

        }

        public void FillPingInfo(MonitorPingInfo monitorPingInfo, MonitorIP monIP)
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


    }
}