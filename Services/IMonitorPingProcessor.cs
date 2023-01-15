using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using NetworkMonitor.Objects;
using NetworkMonitor.Objects.ServiceMessage;
namespace NetworkMonitor.Processor.Services
{
    public interface IMonitorPingProcessor
    {
        void init(ProcessorInitObj initObj);
        void AddMonitorIPsToQueueDic(ProcessorQueueDicObj queueObj);
        ResultObj Connect(ProcessorConnectObj connectObj);
        List<ResultObj> UpdateAlertSent(List<int> monitorPingInfoIDs, bool alertSent);
        List<ResultObj> UpdateAlertFlag(List<int> monitorPingInfoIDs, bool alertFlag);
        ResultObj ResetAlert(int monitorPingInfoID);
        void AddRemovePingInfos(List<RemovePingInfo> removePingInfos);
        bool Awake{get;set;}
    }
}