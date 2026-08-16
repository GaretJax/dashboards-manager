(() => {
    function pad(value) {
        return String(value).padStart(2, "0");
    }

    function timezoneValue(ruleForm) {
        return ruleForm.panel.widget.textarea.getAttribute("data-timezone");
    }

    function timeValue(ruleForm) {
        var rule = ruleForm.freq_rules[ruleForm.selected_freq];
        if (rule.byhour && rule.byhour.length) {
            var hours = rule.byhour[0];
            var minutes =
                rule.byminute && rule.byminute.length ? rule.byminute[0] : 0;
            return pad(hours) + ":" + pad(minutes);
        }
        var dtstart = ruleForm.panel.widget.data.dtstart;
        return dtstart
            ? pad(dtstart.getHours()) + ":" + pad(dtstart.getMinutes())
            : "";
    }

    function setTime(ruleForm, value) {
        var rule = ruleForm.freq_rules[ruleForm.selected_freq];
        if (!value) {
            rule.byhour = [];
            rule.byminute = [];
            rule.bysecond = [];
            ruleForm.update();
            return;
        }
        var parts = value.split(":");
        if (parts.length !== 2) {
            return;
        }
        var hours = Number(parts[0]);
        var minutes = Number(parts[1]);
        if (!Number.isInteger(hours) || !Number.isInteger(minutes)) {
            return;
        }
        rule.byhour = [hours];
        rule.byminute = [minutes];
        rule.bysecond = [0];
        ruleForm.update();
    }

    function addTimeControl(ruleForm) {
        var container = recurrence.widget.e("div", {
            class: "recurrence-time-control",
        });
        var timezone = timezoneValue(ruleForm);
        var labelText = recurrence.display.labels.time + ":";
        if (timezone) {
            labelText += " (" + timezone + ")";
        }
        var label = recurrence.widget.e(
            "label",
            { class: "recurrence-label" },
            labelText,
        );
        var input = recurrence.widget.e("input", {
            class: "recurrence-time-input",
            type: "time",
            step: "60",
            value: timeValue(ruleForm),
        });
        input.addEventListener("input", () => {
            setTime(ruleForm, input.value);
        });
        label.appendChild(input);
        container.appendChild(label);
        ruleForm.elements.root.appendChild(container);
    }

    var originalGetDisplayText =
        recurrence.widget.RuleForm.prototype.get_display_text;
    recurrence.widget.RuleForm.prototype.get_display_text = function (short) {
        var text = originalGetDisplayText.call(this, short);
        var time = timeValue(this);
        var timezone = timezoneValue(this);
        if (!time) {
            return text;
        }
        return text + " (" + time + (timezone ? " " + timezone : "") + ")";
    };

    var originalInit = recurrence.widget.RuleForm.prototype.init;
    recurrence.widget.RuleForm.prototype.init = function (
        panel,
        mode,
        rule,
        options,
    ) {
        originalInit.call(this, panel, mode, rule, options);
        addTimeControl(this);
    };
})();
