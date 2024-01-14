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
        Task Init(ProcessorInitObj initObj);
        Task<ResultObj> SetAuthKey(string authkey);
        ResultObj AddMonitorIPsToQueueDic(ProcessorQueueDicObj queueObj);
        Task<ResultObj> Connect(ProcessorConnectObj connectObj);
        ResultObj WakeUp();
        List<ResultObj> UpdateAlertSent(List<int> monitorPingInfoIDs, bool alertSent);
        List<ResultObj> UpdateAlertFlag(List<int> monitorPingInfoIDs, bool alertFlag);
        List<ResultObj> ResetAlerts(List<int> monitorIPIDs);
        void  ProcessesMonitorReturnData(ProcessorDataObj processorDataObj);

        Task<ResultObj> ProcessorUserEvent(ProcessorUserEventObj processorUserEventObj);
        bool Awake{get;set;}
         string AppID { get;  }
    }
}