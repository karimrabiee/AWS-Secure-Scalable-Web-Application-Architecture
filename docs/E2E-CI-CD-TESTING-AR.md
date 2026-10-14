# اختبار CI/CD وEnd-to-End وحل الأخطاء

## نتيجة السجل المرفق

السجل يثبت أن Terraform نجح في إنشاء **70 موردًا**:

```text
Apply complete! Resources: 70 added, 0 changed, 0 destroyed.
```

إذًا المشكلة ليست في `terraform apply`. ظهور `502 Bad Gateway` يعني أن ALB وصل إلى Nginx، لكن Nginx لم يجد Gunicorn/Flask جاهزًا خلفه أو أن Target Group ما زالت تعتبر الـ instance غير صحية. في أول دقائق بعد إنشاء ASG هذا متوقع؛ User Data يثبت Python packages وNginx وGunicorn ويحتاج عدة دقائق.

ظهر أيضًا خطأ PowerShell لأن الرمز `\\` يستخدم لتكملة الأوامر في Linux، وليس في PowerShell. في PowerShell استخدم أمرًا في سطر واحد أو backtick `` ` ``.

## A. اختبار CI

### اختبار Pull Request

1. أنشئ branch جديدًا:

```bash
git checkout -b test/ci-validation
echo "CI validation" >> docs/CI-CD.md
git add docs/CI-CD.md
git commit -m "Test CI validation"
git push -u origin test/ci-validation
```

2. افتح Pull Request إلى `main`.
3. افتح GitHub → Actions.
4. يجب أن يعمل Workflow باسم `CI`.
5. يجب أن تنجح jobs التالية:

- Python tests and quality.
- Terraform validation، بثلاثة matrix entries:
  - bootstrap
  - dev
  - prod
- Repository hygiene.

هذه المرحلة لا تحتاج AWS credentials لأنها تستخدم:

```bash
terraform init -backend=false
terraform validate
```

بعد نجاح CI ادمج Pull Request أو احذف التغيير التجريبي.

### اختبار Push إلى main

بعد الدمج، يجب أن يعمل `CI` مرة أخرى على `main`. لا يعتبر هذا اختبار CD؛ هو اختبار جودة فقط.

## B. اختبار CD بدون إنشاء موارد

من GitHub:

```text
Actions → Terraform deploy (manual) → Run workflow
```

اختر:

```text
Branch: main
Environment: dev
apply: false
```

النتيجة المتوقعة بالترتيب:

1. `actions/checkout` يحمّل الكود.
2. Terraform 1.10.5 يتم تجهيزه.
3. OIDC يسجل الدخول إلى AWS بدون Access Keys.
4. خطوة `Verify AWS identity` تطبع الحساب والـ assumed role.
5. Terraform يفتح S3 backend الصحيح.
6. `terraform validate` ينجح.
7. `terraform plan` ينجح.
8. يتم رفع artifact اسمه `terraform-plan-dev`.
9. لا يتم تشغيل `apply` لأن `apply=false`.

في خطوة الهوية ابحث عن:

```json
"Account": "YOUR_ACCOUNT_ID",
"Arn": "arn:aws:sts::YOUR_ACCOUNT_ID:assumed-role/GitHubActions-Terraform-Dev/..."
```

إذا ظهر حساب أو Role خطأ، أوقف الاختبار ولا تشغّل apply.

> تشغيل `apply=false` في Workflow منفصل لا يعني أن خطة هذا التشغيل سيتم تطبيقها في Workflow لاحق. عند تشغيل `apply=true` يتم إنشاء خطة جديدة ثم تطبيقها في نفس التشغيل. لذلك يجب مراجعة خطة التشغيل الذي سيقوم بالتطبيق.

## C. اختبار CD مع Dev

بعد نجاح plan، شغّل Workflow جديدًا:

```text
Environment: dev
apply: true
```

هذا التشغيل يقوم بـ plan ثم apply في نفس الـ run. إذا كانت حماية Environment مفعلة، ستظهر خطوة موافقة قبل apply.

لا توافق قبل مراجعة:

- AWS Account.
- Region.
- عدد الموارد.
- وجود `destroy` أو `replace`.
- DB instance class.
- اسم S3 state key.

## D. التحقق من حالة AWS بعد apply

من PowerShell داخل `terraform/environments/dev`:

```powershell
$env:AWS_PROFILE = "portfolio"
$env:AWS_REGION = "us-east-1"
aws sts get-caller-identity
$ALB = terraform output -raw alb_dns_name
Write-Host $ALB
```

انتظر من **5 إلى 10 دقائق** بعد إنشاء ASG قبل اختبار ALB. User Data يحتاج وقتًا لتثبيت packages وتشغيل الخدمات.

اختبر من PowerShell:

```powershell
Invoke-WebRequest "http://$ALB/health" -UseBasicParsing
Invoke-WebRequest "http://$ALB/" -UseBasicParsing
```

المتوقع:

```text
StatusCode: 200
Content: OK
```

في Linux/macOS:

```bash
ALB=$(terraform output -raw alb_dns_name)
curl -i --max-time 15 "http://$ALB/health"
curl -i --max-time 15 "http://$ALB/"
```

## E. فحص Target Group

اسم Target Group في Dev هو:

```text
ecomm-platform-dev-tg
```

PowerShell:

```powershell
$TG_ARN = aws elbv2 describe-target-groups `
  --names ecomm-platform-dev-tg `
  --query 'TargetGroups[0].TargetGroupArn' `
  --output text

aws elbv2 describe-target-health `
  --target-group-arn $TG_ARN `
  --output table
```

Linux/macOS:

```bash
TG_ARN=$(aws elbv2 describe-target-groups \
  --names ecomm-platform-dev-tg \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

aws elbv2 describe-target-health \
  --target-group-arn "$TG_ARN" \
  --output table
```

الحالة الصحيحة:

```text
State: healthy
```

الأسباب الشائعة:

| State/Reason | المعنى | الإجراء |
|---|---|---|
| `initial` | ALB ما زال ينتظر الفحص | انتظر عدة دقائق |
| `unhealthy` + timeout | لا يوجد رد من Nginx | افحص الخدمة وSecurity Group |
| `unhealthy` + 502 | Nginx يعمل لكن Gunicorn لا يعمل | افحص `ecomm-app.service` |
| `unhealthy` + connection refused | لا يوجد process على port 80 | افحص Nginx وUser Data |

## F. فحص EC2 عبر SSM

اعرض Instance IDs داخل ASG:

PowerShell:

```powershell
$INSTANCE_ID = aws autoscaling describe-auto-scaling-groups `
  --auto-scaling-group-names Dev-ASG `
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' `
  --output text

Write-Host $INSTANCE_ID
aws ssm describe-instance-information `
  --filters "Key=InstanceIds,Values=$INSTANCE_ID" `
  --output table
```

يجب أن تكون Instance ظاهرة في SSM. إذا لم تظهر، تحقق من:

- IAM instance profile.
- SSM Agent.
- NAT Gateway وprivate route.
- Security Group egress.

شغّل فحوص التطبيق بدون SSH:

```powershell
$COMMAND_ID = aws ssm send-command `
  --instance-ids $INSTANCE_ID `
  --document-name "AWS-RunShellScript" `
  --parameters 'commands=["sudo systemctl is-active ecomm-app","sudo systemctl is-active nginx","curl -fsS http://127.0.0.1/health","sudo journalctl -u ecomm-app -n 80 --no-pager","sudo nginx -t","sudo tail -n 100 /var/log/cloud-init-output.log"]' `
  --query 'Command.CommandId' `
  --output text

aws ssm wait command-executed `
  --command-id $COMMAND_ID `
  --instance-id $INSTANCE_ID

aws ssm get-command-invocation `
  --command-id $COMMAND_ID `
  --instance-id $INSTANCE_ID `
  --query '{Status:Status,Output:StandardOutputContent,Error:StandardErrorContent}' `
  --output json
```

النتيجة الصحيحة:

```text
active
active
OK
```

لا تنشر مخرجات `journalctl` أو ملفات bootstrap الداخلية في GitHub أو في تقرير عام؛ قد تحتوي على معلومات داخلية.

## G. تفسير 502 وحلها

### الحالة الأولى: حدث 502 مباشرة بعد apply

هذا غالبًا طبيعي. انتظر 5–10 دقائق، ثم افحص Target Group. لا تعيد `terraform apply` لمجرد أن ALB أعاد 502 مباشرة بعد إنشاء ASG.

### الحالة الثانية: Target healthy لكن ما زال 502

افحص من SSM:

```bash
sudo systemctl status ecomm-app --no-pager
sudo systemctl status nginx --no-pager
curl -i http://127.0.0.1/health
curl -i http://127.0.0.1:8000/health
```

إذا كان port `8000` لا يعمل، اقرأ:

```bash
sudo journalctl -u ecomm-app -n 100 --no-pager
```

أسباب محتملة:

- فشل `pip install` بسبب عدم وجود NAT أو Internet route.
- فشل User Data قبل إنشاء systemd service.
- خطأ في Python dependency.
- مشكلة في Nginx configuration.

اقرأ User Data log:

```bash
sudo tail -n 200 /var/log/cloud-init-output.log
```

### الحالة الثالثة: Target unhealthy

لا تبدأ بتعديل ALB. افحص بالترتيب:

```text
SSM managed؟
  ↓
cloud-init نجح؟
  ↓
ecomm-app active؟
  ↓
nginx active؟
  ↓
curl localhost/health ينجح؟
  ↓
Target Group healthy؟
```

## H. اختبار End-to-End الكامل

نفّذ هذا السيناريو وسجّل النتيجة:

| الاختبار | الأمر/المكان | النتيجة المطلوبة |
|---|---|---|
| AWS identity | `aws sts get-caller-identity` | الحساب الصحيح |
| GitHub CI | Pull Request | كل jobs خضراء |
| OIDC | Workflow log | assumed role صحيح |
| Backend | Terraform init | S3 state initialized |
| Terraform | validate/plan | بدون أخطاء |
| Deploy | Workflow apply | Apply complete |
| ALB | `/health` | HTTP 200 و`OK` |
| Home page | `/` | HTML وAZ وInstance ID |
| Target Group | `describe-target-health` | جميع targets healthy |
| ASG | Console أو CLI | desired/healthy instances صحيحة |
| SSM | `describe-instance-information` | instance managed |
| RDS | AWS Console | Available |
| WAF | CloudWatch/Console | Web ACL associated |
| Logs | CloudWatch | logs تصل بدون أسرار |
| Cleanup | destroy dev | لا توجد موارد Dev غير لازمة |

## I. أمر PowerShell الصحيح للاعتماديات

الأمر الذي فشل في السجل كان Linux-style:

```powershell
python -m pip install \
  -r terraform/modules/compute/app-src/requirements.txt \
  -r requirements-dev.txt
```

الصحيح في PowerShell هو سطر واحد:

```powershell
python -m pip install -r terraform/modules/compute/app-src/requirements.txt -r requirements-dev.txt
```

أو باستخدام backtick:

```powershell
python -m pip install `
  -r terraform/modules/compute/app-src/requirements.txt `
  -r requirements-dev.txt
```

## J. متى تعتبر العملية ناجحة؟

اعتبر Dev ناجحًا فقط عندما تتحقق كل الشروط التالية:

1. CI ناجح على Pull Request.
2. CD plan ناجح.
3. AWS identity تعرض الحساب والـ Role الصحيحين.
4. Terraform apply مكتمل.
5. Target Group كلها `healthy`.
6. `/health` يرجع HTTP 200.
7. `/` يرجع HTTP 200.
8. SSM يرى Instances.
9. RDS حالته `Available`.
10. لا توجد أسرار في logs أو outputs العامة.

بعد انتهاء الاختبار احذف Dev لتجنب تكاليف NAT Gateway وRDS:

```powershell
terraform plan -destroy -out=dev-destroy.tfplan
terraform apply dev-destroy.tfplan
```

لا تحذف Bootstrap قبل التأكد أن لا توجد بيئة تستخدم State bucket.


## K. إصلاح حالة OIDC الفعلية من سجل GitHub

إذا ظهر:

```text
Could not assume role with OIDC: The web identity token provided could not be validated
```

فقارن ثلاثة أشياء: حساب AWS، اسم Repository، واسم GitHub Environment.

في الحالة التي ظهرت في سجل المراجعة كان الحساب الحقيقي هو `768477844931`، بينما كان Repository variable يحتوي ARN لحساب مختلف، وكانت Trust Policy تستخدم `:dev` بدل `:environment:dev`.

Trust Policy الصحيحة لـ Dev يجب أن تحتوي على:

```json
"token.actions.githubusercontent.com:sub": "repo:karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture:environment:dev"
```

وتكون قيمة `AWS_DEPLOY_ROLE_ARN` في GitHub Environment `dev`:

```text
arn:aws:iam::768477844931:role/GitHubActions-Terraform-Dev
```

ولـ Prod:

```json
"token.actions.githubusercontent.com:sub": "repo:karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture:environment:prod"
```

وقيمة `AWS_DEPLOY_ROLE_ARN` في GitHub Environment `prod`:

```text
arn:aws:iam::768477844931:role/GitHubActions-Terraform-Prod
```

ضع المتغيرات داخل Environment `dev` وEnvironment `prod`، وليس Repository variables العامة. احذف أو صحح القيم العامة القديمة حتى لا يحدث fallback غير مقصود، خصوصًا ARN الذي يحتوي على Account ID غير حسابك.
