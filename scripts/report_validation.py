"""Read-only JD CSV validation. Empty results are valid schemas, not zero account totals."""
import argparse
import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal,InvalidOperation
from pathlib import Path

ADDITIVE=('花费','总订单金额','直接订单金额','间接订单金额','总订单行','点击数','展现数')

def number(value):
    try:result=Decimal(value.strip().replace(',',''))
    except InvalidOperation as exc:raise ValueError('报表包含非数字指标') from exc
    if not result.is_finite():raise ValueError('报表包含非有限数值')
    return result

def validate(path,start,end,expected_fields=None):
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>last:raise ValueError('日期倒置')
    raw=Path(path).read_bytes()
    if not raw:raise ValueError('文件为空')
    text=raw.decode('utf-8-sig');rows=[row for row in csv.reader(io.StringIO(text,newline='')) if any(cell.strip() for cell in row)]
    if not rows:raise ValueError('缺少CSV表头')
    fields=rows[0]
    if len(set(fields))!=len(fields):raise ValueError('重复字段')
    if not {'花费','总订单金额','投产比'}.issubset(fields) or fields[0] not in ('下单时间','日期'):raise ValueError('报表字段未知')
    if expected_fields is not None and fields!=expected_fields:raise ValueError('报表维度字段与预期不符')
    indices={name:fields.index(name) for name in ADDITIVE if name in fields};sums={name:Decimal(0) for name in indices};roi_checks=0;seen=set()
    for row in rows[1:]:
        if len(row)!=len(fields):raise ValueError('CSV行列长度不一致')
        match=re.fullmatch(r'(\d{8})(?:~(\d{8}))?',row[0])
        if not match:raise ValueError('未知日期值')
        dates=[date(int(value[:4]),int(value[4:6]),int(value[6:])) for value in (match[1],match[2] or match[1])]
        if dates[0]>dates[1] or dates[0]<first or dates[1]>last:raise ValueError('数据日期超出请求范围')
        seen.add(row[0]);values={name:number(row[index]) for name,index in indices.items()}
        for name,value in values.items():sums[name]+=value
        for total,a,b in [('总订单金额','直接订单金额','间接订单金额'),('总订单行','直接订单行','间接订单行')]:
            if all(name in fields for name in (total,a,b)) and abs(number(row[fields.index(total)])-number(row[fields.index(a)])-number(row[fields.index(b)]))>Decimal('0.01'):raise ValueError('直接间接拆分与总计不一致')
        roi=number(row[fields.index('投产比')])
        if values['花费']>0:
            if abs(values['总订单金额']/values['花费']-roi)>Decimal('0.011'):raise ValueError('ROI与总订单金额/花费不一致')
            roi_checks+=1
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'fields':fields,'rows':len(rows)-1,'empty':len(rows)==1,'dates':sorted(seen),'sums':{k:str(v) for k,v in sums.items()},'roi_checks':roi_checks,'state':'validated_local','scope_notice':'单文件内部检查，不代表跨维度或后台账单对账通过'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('file');parser.add_argument('--start',required=True);parser.add_argument('--end',required=True);args=parser.parse_args()
    print(json.dumps(validate(args.file,args.start,args.end),ensure_ascii=False,indent=2))
