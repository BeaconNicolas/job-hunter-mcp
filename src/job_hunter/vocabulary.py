"""Technology terms used to compare job descriptions with the CV.

Each canonical name maps to the regular expressions that recognise it. The CV's
"have" set and a job's "wanted" set are both found with the same list, so a skill
counts only when the CV mentions it.
"""

from __future__ import annotations

import re
from functools import cache

TERMS: dict[str, list[str]] = {
    # Cloud
    "AWS": [r"\baws\b", r"amazon web services"],
    "Azure": [r"\bazure\b"],
    "GCP": [r"\bgcp\b", r"google cloud"],
    "Lambda": [r"\blambda\b"],
    "AWS Glue": [r"\bglue\b"],
    "S3": [r"\bs3\b"],
    "EC2": [r"\bec2\b"],
    "ECS": [r"\becs\b", r"\bfargate\b"],
    "EKS": [r"\beks\b"],
    "ECR": [r"\becr\b"],
    "IAM": [r"\biam\b"],
    "VPC": [r"\bvpc\b"],
    "CloudWatch": [r"\bcloudwatch\b"],
    "CloudFormation": [r"\bcloudformation\b"],
    "AWS CDK": [r"\baws cdk\b", r"\bcdk\b"],
    "CodePipeline": [r"\bcodepipeline\b"],
    "CodeBuild": [r"\bcodebuild\b"],
    "EventBridge": [r"\beventbridge\b"],
    "SQS": [r"\bsqs\b"],
    "SNS": [r"\bsns\b"],
    "Step Functions": [r"\bstep functions?\b"],
    "API Gateway": [r"\bapi gateway\b"],
    "DynamoDB": [r"\bdynamodb\b"],
    "RDS": [r"\brds\b", r"\baurora\b"],
    "SageMaker": [r"\bsagemaker\b"],
    "Cloud9": [r"\bcloud9\b"],
    "Serverless": [r"\bserverless\b"],
    "Multi-account AWS": [r"multi-account", r"cross-account", r"aws organizations", r"control tower"],
    # Infrastructure as code, CI/CD, containers
    "Terraform": [r"\bterraform\b"],
    "Pulumi": [r"\bpulumi\b"],
    "Ansible": [r"\bansible\b"],
    "Infrastructure as code": [r"infrastructure as code", r"\biac\b"],
    "CI/CD": [r"\bci\s*/\s*cd\b", r"\bcicd\b", r"continuous (integration|delivery|deployment)"],
    "GitHub Actions": [r"github actions"],
    "GitLab CI": [r"gitlab[ -]ci", r"\bgitlab\b"],
    "Jenkins": [r"\bjenkins\b"],
    "Azure DevOps": [r"azure devops"],
    "Argo CD": [r"\bargo\s?cd\b", r"\bargocd\b"],
    "Docker": [r"\bdocker\b", r"\bcontaineri[sz]"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Helm": [r"\bhelm\b"],
    "Git": [r"\bgit\b"],
    "Linux": [r"\blinux\b", r"\bubuntu\b", r"\bwsl\b"],
    "Bash": [r"\bbash\b", r"shell script"],
    "Prometheus": [r"\bprometheus\b"],
    "Grafana": [r"\bgrafana\b"],
    "Datadog": [r"\bdatadog\b"],
    "Observability": [r"\bobservability\b"],
    "DevSecOps": [r"\bdevsecops\b"],
    "Networking": [r"\bnetworking\b", r"\btcp/ip\b", r"\bdns\b"],
    # Languages and frameworks
    "Python": [r"\bpython\b"],
    "SQL": [r"\bsql\b"],
    "Java": [r"\bjava\b"],
    "JavaScript": [r"\bjavascript\b"],
    "TypeScript": [r"\btypescript\b"],
    "Go": [r"\bgolang\b", r"\bgo (language|developer|programming)\b"],
    "C#": [r"(?<![\w#])c#"],
    ".NET": [r"\.net\b"],
    "Node.js": [r"\bnode\.?js\b"],
    "React": [r"\breact\b"],
    "Angular": [r"\bangular\b"],
    "R": [r"\br programming\b", r"\brstudio\b", r"\bregression in r\b", r"\br \(regression\)"],
    # Data and machine learning
    "pandas": [r"\bpandas\b"],
    "NumPy": [r"\bnumpy\b"],
    "SciPy": [r"\bscipy\b"],
    "scikit-learn": [r"scikit-learn", r"\bsklearn\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "Keras": [r"\bkeras\b"],
    "PyTorch": [r"\bpytorch\b"],
    "XGBoost": [r"\bxgboost\b"],
    "Machine learning": [r"machine learning", r"\bml\b"],
    "Deep learning": [r"deep learning"],
    "NLP": [r"\bnlp\b", r"natural language processing"],
    "MLOps": [r"\bmlops\b"],
    "Data science": [r"data science", r"data scientist"],
    "ETL": [r"\betl\b", r"\belt\b", r"data pipelines?"],
    "Spark": [r"\bspark\b", r"\bpyspark\b"],
    "Airflow": [r"\bairflow\b"],
    "Kafka": [r"\bkafka\b"],
    "Databricks": [r"\bdatabricks\b"],
    "Snowflake": [r"\bsnowflake\b"],
    "MongoDB": [r"\bmongodb\b"],
    "PostgreSQL": [r"\bpostgres(ql)?\b"],
    "Tableau": [r"\btableau\b"],
    "Power BI": [r"\bpower ?bi\b"],
    "Excel": [r"\bexcel\b"],
    "Statistics": [r"\bstatistic(s|al)\b", r"hypothesis testing"],
    "Optimisation (MILP)": [
        r"\bmilp\b",
        r"linear programming",
        r"mathematical optimi[sz]ation",
        r"operations research",
    ],
}


@cache
def _compiled() -> dict[str, re.Pattern[str]]:
    return {
        name: re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
        for name, patterns in TERMS.items()
    }


def find_terms(text: str) -> set[str]:
    """Canonical names of every known term that appears in the text."""
    return {name for name, pattern in _compiled().items() if pattern.search(text or "")}


def cv_text(cv: dict) -> str:
    """All the CV's words in one string (summary, skills, bullets, tags, projects)."""
    parts: list[str] = [str(cv.get("summary", "")), str(cv.get("basics", {}).get("headline", ""))]
    for group in cv.get("skills", []):
        parts.extend(str(item) for item in group.get("items", []))
    for job in cv.get("experience", []):
        for role in job.get("roles", []):
            parts.append(str(role.get("title", "")))
            for bullet in role.get("bullets", []):
                if isinstance(bullet, dict):
                    parts.append(str(bullet.get("text", "")))
                    parts.extend(t.replace("-", " ") for t in bullet.get("tags", []))
                else:
                    parts.append(str(bullet))
    for project in cv.get("projects", []):
        parts.append(str(project.get("name", "")))
        parts.extend(str(b) for b in project.get("bullets", []))
        parts.extend(t.replace("-", " ") for t in project.get("tags", []))
    for item in cv.get("education", []) + cv.get("certifications", []):
        parts.append(" ".join(str(v) for v in item.values()))
    return "\n".join(parts)


def cv_terms(cv: dict) -> set[str]:
    return find_terms(cv_text(cv))
