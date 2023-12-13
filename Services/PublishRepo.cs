using System;
using System.Collections.Generic;
using System.Linq;
using NetworkMonitor.Objects.ServiceMessage;
using System.Diagnostics;
using Microsoft.Extensions.Logging;
using System.Threading;
using System.Threading.Tasks;
using NetworkMonitor.Utils;
namespace NetworkMonitor.Objects.Repository
{
    public class PublishRepo
    {

        public static ResultObj AlertMessgeResetAlerts(IRabbitRepo rabbitRepo, List<AlertFlagObj> alertFlagObjs, string appID, string authKey)
        {
            var result = new ResultObj();
            try
            {
                var alertServiceAlertObj=new AlertServiceAlertObj(){
                    AppID=appID,
                    AuthKey=authKey,
                    AlertFlagObjs=alertFlagObjs
                };

                rabbitRepo.Publish<AlertServiceAlertObj>("alertMessageResetAlerts", alertServiceAlertObj);
                //DaprRepo.PublishEvent<List<AlertFlagObj>>(_daprClient, "alertMessageResetAlerts", alertFlagObjs);
                result.Success = true;
                result.Message = " Success : sent alertMessageResetAlert message . ";
            }
            catch (Exception e)
            {
                result.Success = false;
                result.Message += " Error : failed to set alertMessageResetAlert. Error was :" + e.Message.ToString();
            }
            return result;
        }

       /* public static void ProcessorResetAlerts(ILogger logger, IRabbitRepo rabbitRepo, Dictionary<string, List<int>> monitorIPDic)
        {
            try
            {
                foreach (KeyValuePair<string, List<int>> kvp in monitorIPDic)
                {
                    var monitorIPIDs = new List<int>(kvp.Value);
                    // Dont publish this at the moment as its causing alerts to refire.
                    rabbitRepo.Publish<List<int>>("processorResetAlerts" + kvp.Key, monitorIPIDs);
                }
            }
            catch (Exception e)
            {
                logger.LogError(" Error : failed to publish ProcessResetAlerts. Error was :" + e.ToString());
            }
        }*/

        public static Task MonitorPingInfosLowPriorityThread(ILogger logger, IRabbitRepo rabbitRepo, List<MonitorPingInfo> monitorPingInfos, List<int> removeMonitorPingInfoIDs, List<RemovePingInfo> removePingInfos, List<SwapMonitorPingInfo> swapMonitorPingInfos, List<PingInfo> pingInfos, string appID, uint piIDKey, bool saveState, IFileRepo fileRepo, string authKey)
        {
            var tcs = new TaskCompletionSource<bool>();

            Thread thread = new Thread(async () =>
            {
                try
                {
                    await PublishRepo.MonitorPingInfos(logger, rabbitRepo, monitorPingInfos, removeMonitorPingInfoIDs, removePingInfos, swapMonitorPingInfos, pingInfos, appID, piIDKey, saveState, fileRepo, authKey);
                    tcs.SetResult(true);
                }
                catch (Exception ex)
                {
                    tcs.SetException(ex);
                }
            });

            thread.Priority = ThreadPriority.Lowest;
            thread.Start();

            return tcs.Task;
        }

        public static async Task<ResultObj> MonitorPingInfos(ILogger logger, IRabbitRepo rabbitRepo, List<MonitorPingInfo> monitorPingInfos, List<int> removeMonitorPingInfoIDs, List<RemovePingInfo> removePingInfos, List<SwapMonitorPingInfo> swapMonitorPingInfos, List<PingInfo> pingInfos, string appID, uint piIDKey, bool saveState, IFileRepo fileRepo, string authKey)
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
                    int countMonPingInfos=monitorPingInfos.Count();
                    //var cutMonitorPingInfos = monitorPingInfos.ConvertAll(x => new MonitorPingInfo(x));
                    //timerStr += " Event (Created Cut MonitorPingInfos) at " + timer.ElapsedMilliseconds + " : ";
                    //var pingInfos = new List<PingInfo>();
                    var monitorStatusAlerts = new List<MonitorStatusAlert>();
                    monitorPingInfos.ForEach(f =>
                    {
                        f.DateEnded = DateTime.UtcNow;
                        //pingInfos.AddRange(f.PingInfos.ToList());
                        var monitorStatusAlert = new MonitorStatusAlert();
                        monitorStatusAlert.ID = f.MonitorIPID;
                        monitorStatusAlert.AppID = appID;
                        monitorStatusAlert.Address = f.Address;
                        monitorStatusAlert.AlertFlag = f.MonitorStatus.AlertFlag;
                        monitorStatusAlert.AlertSent = f.MonitorStatus.AlertSent;
                        monitorStatusAlert.DownCount = f.MonitorStatus.DownCount;
                        monitorStatusAlert.EventTime = f.MonitorStatus.EventTime;
                        monitorStatusAlert.IsUp = f.MonitorStatus.IsUp;
                        monitorStatusAlert.Message = f.MonitorStatus.Message;
                        monitorStatusAlert.UserID = f.UserID;
                        monitorStatusAlert.EndPointType = f.EndPointType;
                        monitorStatusAlert.Timeout = f.Timeout;
                        monitorStatusAlert.AddUserEmail = f.AddUserEmail;
                     monitorStatusAlert.IsEmailVerified = f.IsEmailVerified;
                        monitorStatusAlerts.Add(monitorStatusAlert);
                    }
                    );
                    //timerStr += " Event (Created All PingInfos as List) at " + timer.ElapsedMilliseconds + " : ";
                    var processorDataObj = new ProcessorDataObj();
                    processorDataObj.MonitorPingInfos = monitorPingInfos;
                    processorDataObj.RemoveMonitorPingInfoIDs = removeMonitorPingInfoIDs;
                    processorDataObj.SwapMonitorPingInfos = swapMonitorPingInfos;
                    processorDataObj.MonitorStatusAlerts = null;
                    processorDataObj.PingInfos = pingInfos;
                    processorDataObj.AppID = appID;
                    processorDataObj.PiIDKey = piIDKey;
                    processorDataObj.AuthKey=authKey;


                    var processorDataObjAlert = new ProcessorDataObj();
                    processorDataObjAlert.MonitorPingInfos = null;
                    processorDataObjAlert.MonitorStatusAlerts = monitorStatusAlerts;
                    processorDataObjAlert.PingInfos = new List<PingInfo>();
                    processorDataObjAlert.AppID = appID;
                    processorDataObjAlert.AuthKey=authKey;
                    int countMonStatusAlerts=monitorStatusAlerts.Count();
                    timerStr += " Event (Finished ProcessorDataObj Setup) at " + timer.ElapsedMilliseconds + " : ";
                    rabbitRepo.PublishJsonZ<ProcessorDataObj>("alertUpdateMonitorStatusAlerts", processorDataObjAlert);
                    timerStr += $" Event (Published {countMonStatusAlerts} MonitorStatusAlerts to alertservice) at " + timer.ElapsedMilliseconds + " : ";
                    logger.LogDebug(" Sent ProcessorDataObjAlert to Alert Service :  "+JsonUtils.writeJsonObjectToString<ProcessorDataObj>(processorDataObjAlert));
                    if (pingInfos != null)
                    {
                        result.Message += " Count of PingInfos " + pingInfos.Count() + " . ";
                    }
                    else
                    {
                        result.Message += " Found no first enabled PingInfos. ";
                    }
                    if (saveState)
                    {
                        processorDataObj.RemovePingInfos = removePingInfos;
                        string jsonZ = rabbitRepo.PublishJsonZWithID<ProcessorDataObj>("dataUpdateMonitorPingInfos", processorDataObj, appID);
                        await fileRepo.SaveStateStringAsync("ProcessorDataObj", jsonZ);
                        timerStr += $" Event (Saved {countMonPingInfos} MonitorPingInfos to statestore) at " + timer.ElapsedMilliseconds + " : ";
                        logger.LogDebug(" Sent ProcessorDataObj to Data Service :  "+JsonUtils.writeJsonObjectToString<ProcessorDataObj>(processorDataObj));
                    
                    }
                    //pingInfos = null;
                    //cutMonitorPingInfos = null;
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
        public static void ProcessorReady(ILogger logger, IRabbitRepo rabbitRepo, string appID, bool isReady)
        {
            try
            {
                var processorObj = new ProcessorInitObj();
                processorObj.IsProcessorReady = isReady;
                processorObj.AppID = appID;
                rabbitRepo.Publish<ProcessorInitObj>("processorReady", processorObj);
                logger.LogInformation(" Published event ProcessorItitObj.IsProcessorReady = " + isReady);
            }
            catch (Exception e)
            {
                logger.LogError(" Error : Could not Publish event ProcessorItitObj.IsProcessorReady . Erro was : " + e.Message);
            }
        }

    }
}
