export const DAILY_STATES = ['PASS','FAIL','CRASH','TIMEOUT','SKIP','XFAIL','XPASS','CANCELLED','INCOMPLETE'];
export const DAILY_LABELS = {green:'全部通过',red:'未全通过',blue:'进行中',gray:'未运行'};
export function dailyMonthCells(month) {
  const [year,m] = month.split('-').map(Number);
  const first = new Date(Date.UTC(year,m-1,1));
  const offset = (first.getUTCDay()+6)%7;
  const days=new Date(Date.UTC(year,m,0)).getUTCDate();
  const count=Math.ceil((offset+days)/7)*7;
  return Array.from({length:count},(_,i)=>{
    const day = new Date(Date.UTC(year,m-1,1-offset+i));
    return {date:day.toISOString().slice(0,10),inMonth:day.getUTCMonth()===m-1};
  });
}
export function shiftDailyMonth(month,delta) {
  const [year,m]=month.split('-').map(Number);
  return new Date(Date.UTC(year,m-1+delta,1)).toISOString().slice(0,7);
}
export const dailyRate = n => n==null?'—':`${(n*100).toFixed(1)}%`;
export const dailySeconds = n => n==null?'—':n<60?`${n.toFixed(2)}s`:`${(n/60).toFixed(1)}min`;
