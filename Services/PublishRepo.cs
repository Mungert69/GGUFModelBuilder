using System;
using System.Collections.Generic;
using System.Linq;
using NetworkMonitor.Objects.ServiceMessage;
using Dapr.Client;
using System.Diagnostics;
using Microsoft.Extensions.Logging;
using System.Threading;
namespace NetworkMonitor.Objects.Repository
{
    public class PublishRepo
    {
        public static void ProcessorResetAlerts(ILogger logger, RabbitListener rabbitListener, Dictionary<string, List<int>> monitorIPDic)
        {
            try
            {
                foreach (KeyValuePair<string, List<int>> kvp in monitorIPDic)
                {
                    var monitorIPIDs = new List<int>(kvp.Value);
                    // Dont publish this at the moment as its causing alerts to refire.
                    rabbitListener.Publish<List<int>>( "processorResetAlerts" + kvp.Key, monitorIPIDs);
                }
            }
            catch (Exception e)
            {
                logger.LogError(" Error : failed to publish ProcessResetAlerts. Error was :" + e.ToString());
            }
        }
        public static void MonitorPingInfosLowPriorityThread(ILogger logger, RabbitListener rabbitListener, List<MonitorPingInfo> monitorPingInfos, List<int> removeMonitorPingInfoIDs, List<RemovePingInfo> removePingInfos,List<SwapMonitorPingInfo> swapMonitorPingInfos, string appID, int piIDKey, bool saveState)
        {
            Thread thread = new Thread(delegate ()
                       {
                           PublishRepo.MonitorPingInfos(logger, rabbitListener, monitorPingInfos, removeMonitorPingInfoIDs, removePingInfos,swapMonitorPingInfos, appID, piIDKey, saveState);
                       });
            thread.Priority = ThreadPriority.Lowest;
            thread.Start();
        }
        public  static ResultObj MonitorPingInfos(ILogger logger, RabbitListener rabbitListener, List<MonitorPingInfo> monitorPingInfos, List<int> removeMonitorPingInfoIDs, List<RemovePingInfo> removePingInfos,List<SwapMonitorPingInfo> swapMonitorPingInfos, string appID, int piIDKey, bool saveState)
        {
            // var _daprMetadata = new Dictionary<string, string>();
            //_daprMetadata.Add("ttlInSeconds", "120");
            var result = new ResultObj();
            string timerStr = "TIMER started : ";
            result.Message = "PublishMonitorPingInfos : ";
            var timer = new Stopwatch();
            timer.Start();
            try
            {
                if (monitorPingInfos != null && monitorPingInfos.Count() != 0)
                {
                    var cutMonitorPingInfos = monitorPingInfos.ConvertAll(x => new MonitorPingInfo(x));
                    timerStr += " Event (Created Cut MonitorPingInfos) at " + timer.ElapsedMilliseconds + " : ";
                    var pingInfos = new List<PingInfo>();
                    var monitorStatusAlerts = new List<MonitorStatusAlert>();
                    monitorPingInfos.ForEach(f =>
                    {
                        pingInfos.AddRange(f.PingInfos.ConvertAll(x => new PingInfo(x)));
                        var monitorStatusAlert = new MonitorStatusAlert();
                        monitorStatusAlert.ID = f.MonitorIPID;
                        monitorStatusAlert.AppID=f.AppID;
                        monitorStatusAlert.Address = f.Address;
                        monitorStatusAlert.AlertFlag = f.MonitorStatus.AlertFlag;
                        monitorStatusAlert.AlertSent = f.MonitorStatus.AlertSent;
                        monitorStatusAlert.AppID = f.AppID;
                        monitorStatusAlert.DownCount = f.MonitorStatus.DownCount;
                        monitorStatusAlert.EventTime = f.MonitorStatus.EventTime;
                        monitorStatusAlert.IsUp = f.MonitorStatus.IsUp;
                        monitorStatusAlert.Message = f.MonitorStatus.Message;
                        monitorStatusAlert.UserID = f.UserID;
                        monitorStatusAlert.EndPointType = f.EndPointType;
                        monitorStatusAlert.Timeout = f.Timeout;
                        monitorStatusAlerts.Add(monitorStatusAlert);
                    }
                    );
                    timerStr += " Event (Created All PingInfos as List) at " + timer.ElapsedMilliseconds + " : ";
                    var processorDataObj = new ProcessorDataObj();
                    processorDataObj.MonitorPingInfos = cutMonitorPingInfos;
                    processorDataObj.RemoveMonitorPingInfoIDs = removeMonitorPingInfoIDs;
                    processorDataObj.SwapMonitorPingInfos=swapMonitorPingInfos;
                    processorDataObj.MonitorStatusAlerts = null;
                    processorDataObj.PingInfos = pingInfos;
                    processorDataObj.AppID = appID;
                    processorDataObj.PiIDKey = piIDKey;
                    var processorDataObjAlert = new ProcessorDataObj();
                    processorDataObjAlert.MonitorPingInfos = null;
                    processorDataObjAlert.MonitorStatusAlerts = monitorStatusAlerts;
                    processorDataObjAlert.PingInfos = new List<PingInfo>();
                    processorDataObjAlert.AppID = appID;
                    timerStr += " Event (Finished ProcessorDataObj Setup) at " + timer.ElapsedMilliseconds + " : ";
                    timerStr += " Event (Published MonitorPingInfos to monitorservice) at " + timer.ElapsedMilliseconds + " : ";
                    //DaprRepo.PublishEventJsonZ<ProcessorDataObj>(daprClient, "alertUpdateMonitorStatusAlerts", processorDataObjAlert);
                    rabbitListener.PublishJsonZ<ProcessorDataObj>( "alertUpdateMonitorStatusAlerts", processorDataObjAlert);
                    timerStr += " Event (Published MonitorPingInfos to alertservice) at " + timer.ElapsedMilliseconds + " : ";
                    result.Message += " Published to MonitorService and AlertService. ";
                    var m = monitorPingInfos.FirstOrDefault(w => w.Enabled == true);
                    if (m != null && m.PingInfos != null)
                    {
                        result.Message += " Count of first enabled PingInfos " + monitorPingInfos.Where(w => w.Enabled == true).First().PingInfos.Count() + " . ";
                    }
                    else
                    {
                        result.Message += " Found no first enabled PingInfos. ";
                    }
                    if (saveState)
                    {
                        processorDataObj.RemovePingInfos = removePingInfos;
                        string jsonZ = rabbitListener.PublishJsonZ<ProcessorDataObj>("monitorUpdateMonitorPingInfos", processorDataObj);                    
                        FileRepo.SaveStateString("ProcessorDataObj", jsonZ);
                        timerStr += " Event (Saved MonitorPingInfos to statestore) at " + timer.ElapsedMilliseconds + " : ";
                        result.Message += " Saved MonitorPingInfos to State. ";
                    }
                    pingInfos = null;
                    cutMonitorPingInfos = null;
                    processorDataObj = null;
                    processorDataObjAlert = null;
                }
                logger.LogInformation(timerStr);
                timer.Stop();
                result.Message += " Published event ProcessorItitObj.IsProcessorReady = true ";
                result.Success = true;
                logger.LogInformation(result.Message);
            }
            catch (Exception e)
            {
                result.Message += " Error : Failed to publish events and save data to statestore. Error was : " + e.Message.ToString() + " . ";
                result.Success = false;
                logger.LogError(result.Message);
            }
            return result;
        }
        /*public static void ProcessorReadyThreadOLD(ILogger logger, DaprClient daprClient, string appID, bool isReady)
        {
            Thread thread = new Thread(delegate ()
                                    {
                                        PublishRepo.ProcessorReady(logger, daprClient, appID, isReady);
                                    });
            thread.Start();
        }
        private static void ProcessorReady(ILogger logger, DaprClient daprClient, string appID, bool isReady)
        {
            var processorObj = new ProcessorInitObj();
            processorObj.IsProcessorReady = isReady;
            processorObj.AppID = appID;
            DaprRepo.PublishEvent<ProcessorInitObj>(daprClient, "processorReady", processorObj);
            logger.LogInformation(" Published event ProcessorItitObj.IsProcessorReady = false ");
        }*/
        public static void ProcessorReady(ILogger logger,RabbitListener rabbitListener, string appID, bool isReady)
        {
            var processorObj = new ProcessorInitObj();
            processorObj.IsProcessorReady = isReady;
            processorObj.AppID = appID;
            rabbitListener.Publish<ProcessorInitObj>( "processorReady", processorObj);
            logger.LogInformation(" Published event ProcessorItitObj.IsProcessorReady = true ");
        }
    }
}