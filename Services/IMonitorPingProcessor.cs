using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.ServiceMessage;

namespace NetworkMonitorProcessor.Services
{
    public interface IMonitorPingProcessor
    {
        void init(ProcessorInitObj initObj);

        void AddMonitorIPsToQueueDic(ProcessorQueueDicObj queueObj);
        ResultObj Connect(ProcessorConnectObj connectObj);

        void UpdateAlertSent(List<int> monitorPingInfoIDs, bool alertSent);
        void UpdateAlertFlag(List<int> monitorPingInfoIDs, bool alertFlag);

        void ResetAlert(int monitorPingInfoID);
       
    }
}