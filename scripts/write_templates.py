"""Helper: writes all remaining template/view files in one pass."""
import os, pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent / "schoolms"


def w(rel, content):
    p = BASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  wrote {rel}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. enhanced_report_card.html
# ─────────────────────────────────────────────────────────────────────────────
w("templates/academics/enhanced_report_card.html", r"""{% extends "base.html" %}
{% load static custom_filters %}
{% block title %}Report Card - {{ student.user.get_full_name|default:student.user.username }}{% endblock %}
{% block content %}
<div class="content-card" style="margin-bottom:1rem;">
  <div class="page-heading">
    <div>
      <h1 class="page-title">&#128203; Student Report Card</h1>
      <p class="page-subtitle">{{ student.user.get_full_name|default:student.user.username }} &mdash; {{ term.name|default:"All Terms" }}</p>
    </div>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;">
      <a href="{% url 'academics:download_report_card' student.id %}{% if term %}?term={{ term.id }}{% endif %}" class="btn btn-primary" target="_blank">&#11015; Download PDF</a>
      <button onclick="window.print()" class="btn btn-secondary">&#128438; Print</button>
      {% if can_manage %}<a href="{% url 'academics:ai_comment_page' %}?student={{ student.id }}" class="btn btn-secondary">&#129302; AI Comment</a>{% endif %}
    </div>
  </div>
</div>
<div id="reportCard" class="content-card" style="max-width:900px;margin:0 auto;padding:2rem;">
  <div style="text-align:center;margin-bottom:1.5rem;border-bottom:3px solid #1e3a5f;padding-bottom:1rem;">
    <h2 style="color:#1e3a5f;font-size:1.5rem;margin:0;">{{ school.name|upper }}</h2>
    {% if school.address %}<p style="margin:4px 0;color:#555;font-size:.9rem;">{{ school.address }}</p>{% endif %}
    {% if school.phone %}<p style="margin:0;color:#555;font-size:.9rem;">Tel: {{ school.phone }}</p>{% endif %}
    <h3 style="margin-top:1rem;color:#1e3a5f;letter-spacing:2px;font-size:1.1rem;">STUDENT REPORT CARD</h3>
    {% if term %}<p style="color:#666;font-size:.9rem;margin:0;">{{ term.name }}</p>{% endif %}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem 2rem;margin-bottom:1.5rem;font-size:.9rem;">
    <div><b style="color:#1e3a5f;">Student Name:</b> {{ student.user.get_full_name|default:student.user.username }}</div>
    <div><b style="color:#1e3a5f;">Admission No.:</b> {{ student.admission_number|default:"&mdash;" }}</div>
    <div><b style="color:#1e3a5f;">Class:</b> {{ student.class_name|default:"&mdash;" }}</div>
    <div><b style="color:#1e3a5f;">Academic Year:</b> {{ school.academic_year|default:"&mdash;" }}</div>
    <div><b style="color:#1e3a5f;">Term:</b> {{ term.name|default:"&mdash;" }}</div>
    <div><b style="color:#1e3a5f;">Date Issued:</b> {% now "d M Y" %}</div>
    <div><b style="color:#1e3a5f;">Attendance:</b> {{ attendance_text|default:"N/A" }}</div>
    <div><b style="color:#1e3a5f;">Term Position:</b> {{ term_position|default:"&mdash;" }}</div>
  </div>
  <h4 style="color:#1e3a5f;margin-bottom:.75rem;border-left:4px solid #1e3a5f;padding-left:.5rem;">Academic Performance</h4>
  <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:.88rem;">
      <thead>
        <tr style="background:#1e3a5f;color:#fff;">
          <th style="padding:8px 12px;text-align:left;border:1px solid #2563eb;">Subject</th>
          <th style="padding:8px;text-align:center;border:1px solid #2563eb;">CA ({{ ca_weight|default:"50" }}%)</th>
          <th style="padding:8px;text-align:center;border:1px solid #2563eb;">Exam ({{ exam_weight|default:"50" }}%)</th>
          <th style="padding:8px;text-align:center;border:1px solid #2563eb;">Final (/100)</th>
          <th style="padding:8px;text-align:center;border:1px solid #2563eb;">Grade</th>
          <th style="padding:8px;text-align:center;border:1px solid #2563eb;">Remarks</th>
        </tr>
      </thead>
      <tbody>
        {% for row in subject_rows %}
        <tr style="background:{% if forloop.counter|divisibleby:2 %}#f7f9fc{% else %}#ffffff{% endif %};">
          <td style="padding:8px 12px;border:1px solid #ddd;font-weight:500;">{{ row.subject }}</td>
          <td style="padding:8px;text-align:center;border:1px solid #ddd;">{{ row.ca|default:"&mdash;" }}</td>
          <td style="padding:8px;text-align:center;border:1px solid #ddd;">{{ row.exam|default:"&mdash;" }}</td>
          <td style="padding:8px;text-align:center;border:1px solid #ddd;font-weight:600;">{{ row.final|default:"&mdash;" }}</td>
          <td style="padding:8px;text-align:center;border:1px solid #ddd;"><b>{{ row.grade }}</b></td>
          <td style="padding:8px;text-align:center;border:1px solid #ddd;font-size:.82rem;">{{ row.remarks|default:"&mdash;" }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="6" style="text-align:center;padding:1.5rem;color:#888;">No results for this term yet. {% if can_manage %}<a href="{% url 'academics:results_management' %}">Add results</a>{% endif %}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p style="font-size:.78rem;color:#888;margin:.5rem 0 1rem;">Grading: CA ({{ ca_weight|default:"50" }}%) + Exam ({{ exam_weight|default:"50" }}%) = Final | A=80-100 B=70-79 C=60-69 D=50-59 F=0-49</p>
  {% if subject_rows %}
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin:1rem 0 1.5rem;text-align:center;">
    <div style="background:#e8f0fe;border-radius:.5rem;padding:.75rem;border:1px solid #9ab0d4;"><div style="font-size:1.4rem;font-weight:700;color:#1e3a5f;">{{ overall_avg|default:"&mdash;" }}%</div><div style="font-size:.78rem;color:#555;">Overall Average</div></div>
    <div style="background:#e8f0fe;border-radius:.5rem;padding:.75rem;border:1px solid #9ab0d4;"><div style="font-size:1.4rem;font-weight:700;color:#1e3a5f;">{{ term_gpa|default:"&mdash;" }}</div><div style="font-size:.78rem;color:#555;">Term GPA</div></div>
    <div style="background:#e8f0fe;border-radius:.5rem;padding:.75rem;border:1px solid #9ab0d4;"><div style="font-size:1.4rem;font-weight:700;color:#1e3a5f;">{{ term_position|default:"&mdash;" }}</div><div style="font-size:.78rem;color:#555;">Term Position</div></div>
    <div style="background:#e8f0fe;border-radius:.5rem;padding:.75rem;border:1px solid #9ab0d4;"><div style="font-size:.9rem;font-weight:700;color:#1e3a5f;">{{ attendance_text|default:"&mdash;" }}</div><div style="font-size:.78rem;color:#555;">Attendance</div></div>
  </div>
  {% endif %}
  <div style="border-top:1px solid #ddd;padding-top:1rem;margin-top:.5rem;">
    <h4 style="color:#1e3a5f;margin-bottom:.5rem;border-left:4px solid #1e3a5f;padding-left:.5rem;">Class Teacher's Comment</h4>
    <div style="background:#f9fafb;border:1px solid #e0e0e0;border-radius:.5rem;padding:1rem;min-height:60px;font-size:.9rem;line-height:1.6;color:#333;">
      {% if ai_comment %}{{ ai_comment.content }}<div style="margin-top:.5rem;font-size:.75rem;color:#888;">AI-generated &bull; {{ ai_comment.created_at|date:"d M Y" }}{% if can_manage %} &bull; <a href="{% url 'academics:ai_comment_page' %}?student={{ student.id }}">Regenerate</a>{% endif %}</div>
      {% else %}<span style="color:#aaa;">No comment yet. {% if can_manage %}<a href="{% url 'academics:ai_comment_page' %}?student={{ student.id }}">Generate AI comment</a>{% endif %}</span>{% endif %}
    </div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:2rem;margin-top:2rem;padding-top:1rem;border-top:1px solid #ddd;font-size:.85rem;">
    <div><div style="border-top:1px solid #888;padding-top:.25rem;color:#333;">Class Teacher</div></div>
    <div><div style="border-top:1px solid #888;padding-top:.25rem;color:#333;">Head Teacher</div></div>
    <div><div style="border-top:1px solid #888;padding-top:.25rem;color:#333;">Parent / Guardian</div></div>
  </div>
  <div style="text-align:center;margin-top:1.5rem;padding-top:.75rem;border-top:1px solid #eee;font-size:.75rem;color:#999;">Official report card from {{ school.name }}. Powered by Mastex SchoolOS.</div>
</div>
<style>@media print{.sidebar,nav,.page-heading .btn,header{display:none!important}body{background:white!important}#reportCard{box-shadow:none!important;border:none!important}}</style>
{% endblock %}
""")


# ─────────────────────────────────────────────────────────────────────────────
# 2. AI Comment page (generate + save)
# ─────────────────────────────────────────────────────────────────────────────
w("templates/academics/ai_comment.html", r"""{% extends "base.html" %}
{% load static %}
{% block title %}AI Comment Generator{% endblock %}
{% block content %}
<div class="content-card">
  <div class="page-heading">
    <div>
      <h1 class="page-title">&#129302; AI Comment Generator</h1>
      <p class="page-subtitle">Generate personalised teacher comments using AI</p>
    </div>
    <a href="{% url 'academics:enhanced_report_card' student.id %}" class="btn btn-secondary">&#8592; Back to Report Card</a>
  </div>
</div>
<div class="content-card" style="max-width:700px;">
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem;padding:1rem;background:#f7f9fc;border-radius:.5rem;">
    <div style="font-size:2rem;">&#127891;</div>
    <div>
      <div style="font-weight:600;font-size:1rem;">{{ student.user.get_full_name|default:student.user.username }}</div>
      <div style="font-size:.85rem;color:#666;">{{ student.class_name|default:"No Class" }} &bull; Admission: {{ student.admission_number|default:"N/A" }}</div>
    </div>
  </div>
  {% if saved_comment %}
  <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:.5rem;padding:1rem;margin-bottom:1.5rem;">
    <div style="font-weight:600;color:#16a34a;margin-bottom:.5rem;">&#10004; Current Comment (saved to report card)</div>
    <p style="margin:0;font-size:.9rem;line-height:1.6;">{{ saved_comment.content }}</p>
    <div style="font-size:.75rem;color:#888;margin-top:.5rem;">Generated: {{ saved_comment.created_at|date:"d M Y H:i" }} &bull; Term: {{ saved_comment.term|default:"All Terms" }}</div>
  </div>
  {% endif %}
  <form method="post" id="commentForm">
    {% csrf_token %}
    <input type="hidden" name="student_id" value="{{ student.id }}">
    <div class="form-group">
      <label class="form-label">Select Term</label>
      <select name="term_id" class="form-control">
        <option value="">All Terms</option>
        {% for t in terms %}
        <option value="{{ t.id }}" {% if t.is_current %}selected{% endif %}>{{ t.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Additional Instructions (optional)</label>
      <input type="text" name="instructions" class="form-control" placeholder="e.g. Focus on maths improvement, mention good behaviour">
    </div>
    <div style="display:flex;gap:.75rem;flex-wrap:wrap;">
      <button type="submit" name="action" value="generate" class="btn btn-primary" id="generateBtn">
        &#9889; Generate AI Comment
      </button>
      {% if generated_comment %}
      <button type="submit" name="action" value="save" class="btn btn-success">
        &#10003; Save to Report Card
      </button>
      {% endif %}
    </div>
  </form>
  {% if generated_comment %}
  <div style="margin-top:1.5rem;background:#eff6ff;border:1px solid #93c5fd;border-radius:.5rem;padding:1rem;">
    <div style="font-weight:600;color:#1e40af;margin-bottom:.5rem;">&#129302; Generated Comment (preview)</div>
    <p style="margin:0;font-size:.9rem;line-height:1.6;">{{ generated_comment }}</p>
    <input type="hidden" name="generated_comment" value="{{ generated_comment }}">
  </div>
  {% endif %}
  {% if error %}
  <div style="margin-top:1rem;background:#fef2f2;border:1px solid #fca5a5;border-radius:.5rem;padding:1rem;color:#dc2626;">
    {{ error }}
  </div>
  {% endif %}
</div>
<script>
document.getElementById('generateBtn')?.addEventListener('click', function() {
  this.textContent = '&#9889; Generating...';
  this.disabled = true;
});
</script>
{% endblock %}
""")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Receipt PDF template
# ─────────────────────────────────────────────────────────────────────────────
w("templates/operations/receipt.html", r"""{% extends "base.html" %}
{% load static %}
{% block title %}Receipt #{{ payment.id }} | {{ school.name }}{% endblock %}
{% block content %}
<div class="content-card" style="margin-bottom:1rem;">
  <div class="page-heading">
    <div>
      <h1 class="page-title">&#129534; Payment Receipt</h1>
      <p class="page-subtitle">Receipt #{{ payment.id }}</p>
    </div>
    <div style="display:flex;gap:.5rem;">
      <a href="{% url 'operations:receipt_pdf' payment.id %}" class="btn btn-primary" target="_blank">&#11015; Download PDF</a>
      <button onclick="window.print()" class="btn btn-secondary">&#128438; Print</button>
    </div>
  </div>
</div>
<div id="receipt" class="content-card" style="max-width:600px;margin:0 auto;padding:2rem;">
  <div style="text-align:center;border-bottom:2px solid #1e3a5f;padding-bottom:1rem;margin-bottom:1.5rem;">
    <h2 style="color:#1e3a5f;margin:0;font-size:1.4rem;">{{ school.name|upper }}</h2>
    {% if school.address %}<p style="margin:2px 0;color:#555;font-size:.85rem;">{{ school.address }}</p>{% endif %}
    {% if school.phone %}<p style="margin:0;color:#555;font-size:.85rem;">Tel: {{ school.phone }}</p>{% endif %}
    <h3 style="margin-top:.75rem;color:#1e3a5f;font-size:1rem;letter-spacing:2px;">OFFICIAL RECEIPT</h3>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem 1.5rem;font-size:.88rem;margin-bottom:1.5rem;">
    <div><b style="color:#1e3a5f;">Receipt No.:</b> #{{ payment.id }}</div>
    <div><b style="color:#1e3a5f;">Date:</b> {{ payment.paid_at|date:"d M Y H:i"|default:payment.created_at|date:"d M Y H:i" }}</div>
    <div><b style="color:#1e3a5f;">Student:</b> {{ payment.student.user.get_full_name|default:payment.student }}</div>
    <div><b style="color:#1e3a5f;">Class:</b> {{ payment.student.class_name|default:"&mdash;" }}</div>
    <div><b style="color:#1e3a5f;">Fee Type:</b> {{ payment.get_fee_type_display|default:payment.fee_type }}</div>
    <div><b style="color:#1e3a5f;">Payment Method:</b> {{ payment.get_method_display|default:payment.method|default:"Online" }}</div>
    {% if payment.reference %}<div><b style="color:#1e3a5f;">Reference:</b> {{ payment.reference }}</div>{% endif %}
    {% if payment.period_label %}<div><b style="color:#1e3a5f;">Period:</b> {{ payment.period_label }}</div>{% endif %}
  </div>
  <div style="background:#f7f9fc;border:1px solid #ddd;border-radius:.5rem;padding:1rem;margin-bottom:1.5rem;">
    <table style="width:100%;border-collapse:collapse;font-size:.9rem;">
      <tr style="border-bottom:1px solid #ddd;">
        <td style="padding:6px 0;font-weight:600;color:#1e3a5f;">Description</td>
        <td style="padding:6px 0;text-align:right;font-weight:600;color:#1e3a5f;">Amount</td>
      </tr>
      <tr>
        <td style="padding:8px 0;">{{ payment.get_fee_type_display|default:payment.description|default:"School Fee Payment" }}
          {% if payment.period_label %}<br><small style="color:#666;">{{ payment.period_label }}</small>{% endif %}</td>
        <td style="padding:8px 0;text-align:right;font-size:1.1rem;font-weight:600;">{{ school.currency|default:"GHS" }} {{ payment.amount|floatformat:2 }}</td>
      </tr>
      {% if payment.balance_before is not None %}
      <tr style="border-top:1px solid #eee;">
        <td style="padding:4px 0;color:#888;font-size:.82rem;">Balance before payment</td>
        <td style="padding:4px 0;text-align:right;color:#888;font-size:.82rem;">{{ school.currency|default:"GHS" }} {{ payment.balance_before|floatformat:2 }}</td>
      </tr>
      <tr>
        <td style="padding:4px 0;color:#16a34a;font-size:.82rem;">Balance after payment</td>
        <td style="padding:4px 0;text-align:right;color:#16a34a;font-size:.82rem;">{{ school.currency|default:"GHS" }} {{ payment.balance_after|floatformat:2 }}</td>
      </tr>
      {% endif %}
    </table>
  </div>
  <div style="text-align:center;background:{% if payment.status == 'paid' %}#f0fdf4{% else %}#fef9c3{% endif %};border:1px solid {% if payment.status == 'paid' %}#86efac{% else %}#fde047{% endif %};border-radius:.5rem;padding:.75rem;margin-bottom:1.5rem;">
    <span style="font-weight:700;font-size:1rem;color:{% if payment.status == 'paid' %}#16a34a{% else %}#ca8a04{% endif %};">
      {% if payment.status == 'paid' %}&#10004; PAYMENT CONFIRMED{% else %}&#9203; PENDING{% endif %}
    </span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin-top:2rem;padding-top:1rem;border-top:1px solid #ddd;font-size:.82rem;text-align:center;">
    <div><div style="border-top:1px solid #888;padding-top:.25rem;">Cashier / Accountant</div></div>
    <div><div style="border-top:1px solid #888;padding-top:.25rem;">Parent / Guardian</div></div>
  </div>
  <div style="text-align:center;margin-top:1.5rem;font-size:.72rem;color:#aaa;">
    Thank you for your payment. This is an official receipt from {{ school.name }}. Powered by Mastex SchoolOS.
  </div>
</div>
<style>@media print{.sidebar,nav,.page-heading .btn,header{display:none!important}body{background:white!important}#receipt{box-shadow:none!important;border:none!important}}</style>
{% endblock %}
""")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Super-admin metrics/charts dashboard
# ─────────────────────────────────────────────────────────────────────────────
w("templates/accounts/superadmin_metrics.html", r"""{% extends "base.html" %}
{% load static %}
{% block title %}Super Admin Metrics | Mastex SchoolOS{% endblock %}
{% block extra_css %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
{% endblock %}
{% block content %}
<div class="content-card" style="margin-bottom:1rem;">
  <div class="page-heading">
    <div>
      <h1 class="page-title">&#128202; Super Admin Metrics</h1>
      <p class="page-subtitle">Platform-wide analytics &amp; subscription overview</p>
    </div>
    <div style="display:flex;gap:.5rem;">
      <a href="?export=csv" class="btn btn-secondary">&#11015; Export CSV</a>
    </div>
  </div>
</div>

<!-- KPI Cards -->
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;margin-bottom:1.5rem;">
  {% for kpi in kpis %}
  <div class="content-card" style="padding:1.25rem;border-left:4px solid {{ kpi.color }};">
    <div style="font-size:1.8rem;font-weight:700;color:{{ kpi.color }};">{{ kpi.value }}</div>
    <div style="font-size:.85rem;color:#666;margin-top:.25rem;">{{ kpi.label }}</div>
    {% if kpi.change is not None %}
    <div style="font-size:.75rem;margin-top:.25rem;color:{% if kpi.change >= 0 %}#16a34a{% else %}#dc2626{% endif %};">
      {% if kpi.change >= 0 %}&#9650;{% else %}&#9660;{% endif %} {{ kpi.change|floatformat:1 }}% this month
    </div>
    {% endif %}
  </div>
  {% endfor %}
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem;">
  <!-- Subscription Trend -->
  <div class="content-card" style="padding:1.5rem;">
    <h3 style="color:#1e3a5f;margin-bottom:1rem;">Subscription Trend (12 months)</h3>
    <canvas id="subChart" height="200"></canvas>
  </div>
  <!-- Revenue Trend -->
  <div class="content-card" style="padding:1.5rem;">
    <h3 style="color:#1e3a5f;margin-bottom:1rem;">Monthly Revenue</h3>
    <canvas id="revChart" height="200"></canvas>
  </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem;">
  <!-- Plan breakdown pie -->
  <div class="content-card" style="padding:1.5rem;">
    <h3 style="color:#1e3a5f;margin-bottom:1rem;">Schools by Plan</h3>
    <canvas id="planChart" height="220"></canvas>
  </div>
  <!-- Active vs expired -->
  <div class="content-card" style="padding:1.5rem;">
    <h3 style="color:#1e3a5f;margin-bottom:1rem;">Subscription Status</h3>
    <canvas id="statusChart" height="220"></canvas>
  </div>
</div>

<!-- Schools table -->
<div class="content-card" style="padding:1.5rem;">
  <h3 style="color:#1e3a5f;margin-bottom:1rem;">All Schools</h3>
  <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:.87rem;">
      <thead>
        <tr style="background:#1e3a5f;color:#fff;">
          <th style="padding:8px 12px;text-align:left;">School</th>
          <th style="padding:8px;text-align:center;">Plan</th>
          <th style="padding:8px;text-align:center;">Status</th>
          <th style="padding:8px;text-align:center;">Students</th>
          <th style="padding:8px;text-align:center;">Expires</th>
          <th style="padding:8px;text-align:center;">Revenue</th>
          <th style="padding:8px;text-align:center;">Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for s in schools %}
        <tr style="background:{% if forloop.counter|divisibleby:2 %}#f7f9fc{% else %}#ffffff{% endif %};">
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:500;">{{ s.name }}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #eee;"><span style="background:#e8f0fe;color:#1e3a5f;border-radius:9999px;padding:2px 8px;font-size:.78rem;">{{ s.subscription_plan|default:"basic" }}</span></td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #eee;">
            <span style="background:{% if s.subscription_active %}#f0fdf4{% else %}#fef2f2{% endif %};color:{% if s.subscription_active %}#16a34a{% else %}#dc2626{% endif %};border-radius:9999px;padding:2px 8px;font-size:.78rem;">
              {% if s.subscription_active %}Active{% else %}Expired{% endif %}
            </span>
          </td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #eee;">{{ s.student_count|default:0 }}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #eee;">{{ s.subscription_expiry|date:"d M Y"|default:"&mdash;" }}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #eee;">{{ s.currency|default:"GHS" }} {{ s.total_revenue|default:0|floatformat:2 }}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #eee;">
            <a href="/schools/{{ s.id }}/dashboard/" class="btn btn-sm btn-secondary">View</a>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="7" style="text-align:center;padding:1.5rem;color:#888;">No schools found.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<script>
const months = {{ chart_months|safe }};
const subData = {{ chart_subs|safe }};
const revData = {{ chart_revenue|safe }};
const planLabels = {{ plan_labels|safe }};
const planValues = {{ plan_values|safe }};
const statusLabels = ['Active', 'Expired', 'Trial'];
const statusValues = {{ status_values|safe }};

new Chart(document.getElementById('subChart'), {
  type: 'line',
  data: { labels: months, datasets: [{ label: 'New Subscriptions', data: subData, borderColor: '#1e3a5f', backgroundColor: 'rgba(30,58,95,.1)', tension: .4, fill: true }] },
  options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
});

new Chart(document.getElementById('revChart'), {
  type: 'bar',
  data: { labels: months, datasets: [{ label: 'Revenue', data: revData, backgroundColor: '#2563eb', borderRadius: 6 }] },
  options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
});

new Chart(document.getElementById('planChart'), {
  type: 'doughnut',
  data: { labels: planLabels, datasets: [{ data: planValues, backgroundColor: ['#1e3a5f','#2563eb','#60a5fa','#93c5fd','#bfdbfe'] }] },
  options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
});

new Chart(document.getElementById('statusChart'), {
  type: 'doughnut',
  data: { labels: statusLabels, datasets: [{ data: statusValues, backgroundColor: ['#16a34a','#dc2626','#d97706'] }] },
  options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
});
</script>
{% endblock %}
""")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Flexible partial payment template
# ─────────────────────────────────────────────────────────────────────────────
w("templates/operations/partial_payment.html", r"""{% extends "base.html" %}
{% load static %}
{% block title %}Pay {{ fee_type_label }} | {{ school.name }}{% endblock %}
{% block content %}
<div class="content-card" style="margin-bottom:1rem;">
  <div class="page-heading">
    <div>
      <h1 class="page-title">&#128178; Pay {{ fee_type_label }}</h1>
      <p class="page-subtitle">Partial &amp; instalment payments are accepted</p>
    </div>
    <a href="{{ back_url }}" class="btn btn-secondary">&#8592; Back</a>
  </div>
</div>
<div class="content-card" style="max-width:550px;">
  <!-- Summary -->
  <div style="background:#f7f9fc;border-radius:.5rem;padding:1rem;margin-bottom:1.5rem;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem;font-size:.9rem;">
      <div><b style="color:#1e3a5f;">Fee Type:</b> {{ fee_type_label }}</div>
      <div><b style="color:#1e3a5f;">Student:</b> {{ student.user.get_full_name|default:student }}</div>
      <div><b style="color:#1e3a5f;">Total Fee:</b> {{ currency }} {{ total_fee|floatformat:2 }}</div>
      <div><b style="color:#1e3a5f;">Paid:</b> {{ currency }} {{ total_paid|floatformat:2 }}</div>
      <div><b style="color:#dc2626;">Balance:</b> <b>{{ currency }} {{ balance|floatformat:2 }}</b></div>
      <div><b style="color:#1e3a5f;">Status:</b>
        {% if balance <= 0 %}<span style="color:#16a34a;">&#10004; Fully Paid</span>
        {% elif total_paid > 0 %}<span style="color:#d97706;">&#8987; Partially Paid</span>
        {% else %}<span style="color:#dc2626;">&#9940; Unpaid</span>{% endif %}
      </div>
    </div>
  </div>

  {% if balance > 0 %}
  <!-- Quick amount buttons -->
  <div style="margin-bottom:1rem;">
    <label class="form-label">Quick Amount</label>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;">
      <button type="button" class="btn btn-secondary btn-sm" onclick="setAmount({{ balance|floatformat:2 }})">Full Balance ({{ currency }} {{ balance|floatformat:2 }})</button>
      <button type="button" class="btn btn-secondary btn-sm" onclick="setAmount({{ half_balance|floatformat:2 }})">Half ({{ currency }} {{ half_balance|floatformat:2 }})</button>
      {% if fee_type == 'bus' %}
      <button type="button" class="btn btn-secondary btn-sm" onclick="setAmount({{ daily_rate|floatformat:2 }})">Daily ({{ currency }} {{ daily_rate|floatformat:2 }})</button>
      <button type="button" class="btn btn-secondary btn-sm" onclick="setAmount({{ weekly_rate|floatformat:2 }})">Weekly ({{ currency }} {{ weekly_rate|floatformat:2 }})</button>
      {% endif %}
    </div>
  </div>

  <form method="post" id="paymentForm">
    {% csrf_token %}
    <input type="hidden" name="fee_type" value="{{ fee_type }}">
    <input type="hidden" name="student_id" value="{{ student.id }}">
    <div class="form-group">
      <label class="form-label">Amount to Pay ({{ currency }}) <span style="color:red;">*</span></label>
      <input type="number" id="amountInput" name="amount" class="form-control" min="1" max="{{ balance }}" step="0.01" required placeholder="Enter amount">
      <small style="color:#888;">Max: {{ currency }} {{ balance|floatformat:2 }}</small>
    </div>
    {% if fee_type == 'bus' %}
    <div class="form-group">
      <label class="form-label">Payment Period</label>
      <select name="period" class="form-control" onchange="updateAmount(this.value)">
        <option value="custom">Custom Amount</option>
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
        <option value="termly">Full Term</option>
      </select>
    </div>
    {% endif %}
    <div class="form-group">
      <label class="form-label">Payment Method</label>
      <select name="method" class="form-control">
        <option value="paystack">Online (Paystack)</option>
        <option value="cash">Cash</option>
        <option value="bank_transfer">Bank Transfer</option>
        <option value="momo">Mobile Money</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Notes (optional)</label>
      <input type="text" name="notes" class="form-control" placeholder="e.g. Week 1 bus payment">
    </div>
    <button type="submit" class="btn btn-primary" style="width:100%;">
      &#128178; Proceed to Payment
    </button>
  </form>
  {% else %}
  <div style="text-align:center;padding:2rem;color:#16a34a;">
    <div style="font-size:3rem;">&#10004;</div>
    <h3>Fully Paid</h3>
    <p>All fees for {{ fee_type_label }} have been paid.</p>
    <a href="{{ back_url }}" class="btn btn-primary">Back</a>
  </div>
  {% endif %}

  <!-- Payment history -->
  {% if payments %}
  <div style="margin-top:2rem;border-top:1px solid #ddd;padding-top:1rem;">
    <h4 style="color:#1e3a5f;margin-bottom:.75rem;">Payment History</h4>
    <table style="width:100%;border-collapse:collapse;font-size:.85rem;">
      <thead>
        <tr style="background:#f0f4f8;">
          <th style="padding:6px 8px;text-align:left;">Date</th>
          <th style="padding:6px 8px;text-align:left;">Period</th>
          <th style="padding:6px 8px;text-align:right;">Amount</th>
          <th style="padding:6px 8px;text-align:center;">Receipt</th>
        </tr>
      </thead>
      <tbody>
        {% for p in payments %}
        <tr>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;">{{ p.created_at|date:"d M Y" }}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;">{{ p.period_label|default:"&mdash;" }}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{{ currency }} {{ p.amount|floatformat:2 }}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:center;">
            <a href="{% url 'operations:receipt_pdf' p.id %}" class="btn btn-sm btn-secondary" target="_blank">PDF</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
</div>

<script>
function setAmount(v) {
  document.getElementById('amountInput').value = v;
}
const dailyRate = {{ daily_rate|default:0 }};
const weeklyRate = {{ weekly_rate|default:0 }};
const monthlyRate = {{ monthly_rate|default:0 }};
const termlyRate = {{ termly_rate|default:0 }};
function updateAmount(period) {
  const map = { daily: dailyRate, weekly: weeklyRate, monthly: monthlyRate, termly: termlyRate };
  if (map[period]) setAmount(map[period]);
}
</script>
{% endblock %}
""")

print("All template files written successfully.")
