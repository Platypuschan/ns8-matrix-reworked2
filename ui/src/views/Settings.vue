<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<template>
  <cv-grid fullWidth>
    <cv-row
      ><cv-column class="page-title"
        ><h2>{{ $t("settings.title") }}</h2></cv-column
      ></cv-row
    >
    <cv-row v-if="error"
      ><cv-column
        ><NsInlineNotification
          kind="error"
          :title="$t('matrix.failed')"
          :description="error"
          :showCloseButton="false" /></cv-column
    ></cv-row>
    <cv-row v-if="config"
      ><cv-column>
        <cv-form @submit.prevent="save">
          <cv-tile light class="section">
            <h3>{{ $t("matrix.homeserver") }}</h3>
            <cv-text-input
              v-model="config.server_name"
              :label="$t('matrix.server_name')"
              placeholder="example.com"
              :disabled="busy || config.configured"
            />
            <p class="hint">{{ $t("matrix.identity_hint") }}</p>
            <cv-text-input
              v-model="config.synapse_domain_name"
              :label="$t('settings.synapse_domain_name')"
              placeholder="matrix.example.com"
              :disabled="busy"
            />
            <cv-text-input
              v-model="config.element_domain_name"
              :label="$t('settings.element_domain_name')"
              placeholder="chat.example.com"
              :disabled="busy"
            />
            <label class="toggle"
              ><input
                type="checkbox"
                v-model="config.lets_encrypt"
                :disabled="busy"
              />
              {{ $t("matrix.certificates") }}</label
            >
            <label class="toggle"
              ><input
                type="checkbox"
                v-model="config.federation"
                :disabled="busy"
              />
              {{ $t("matrix.federation") }}</label
            >
            <label class="toggle"
              ><input
                type="checkbox"
                v-model="config.enable_registration"
                :disabled="busy"
              />
              {{ $t("matrix.registration") }}</label
            >
            <p class="hint">{{ $t("matrix.registration_hint") }}</p>
          </cv-tile>
          <cv-tile light class="section">
            <h3>{{ $t("matrix.authentication") }}</h3>
            <NsComboBox
              v-model="config.ldap_domain"
              :title="$t('settings.ldap_domain')"
              :label="$t('settings.choose_ldap_domain')"
              :options="config.domains_list"
              :acceptUserInput="false"
              :autoFilter="true"
              :disabled="busy"
            />
            <p class="hint">{{ $t("matrix.ldap_hint") }}</p>
            <cv-text-input
              v-model="config.ldap_filter"
              :label="$t('matrix.ldap_filter')"
              :disabled="busy"
              placeholder="(memberOf=CN=matrix-user,OU=Groups,DC=example,DC=com)"
            />
            <label class="toggle"
              ><input
                type="checkbox"
                v-model="config.shared_secret_auth"
                :disabled="busy"
              />
              {{ $t("matrix.shared_secret") }}</label
            >
            <label class="toggle"
              ><input
                type="checkbox"
                v-model="config.use_smarthost"
                :disabled="busy"
              />
              {{ $t("matrix.smarthost") }}</label
            >
            <cv-text-input
              v-if="config.use_smarthost"
              v-model="config.mail_from"
              :label="$t('settings.mail_from')"
              placeholder="matrix@example.com"
              :disabled="busy"
            />
          </cv-tile>
          <cv-tile light class="section">
            <h3>{{ $t("matrix.calls") }}</h3>
            <div v-for="name in ['rtc', 'turn']" :key="name" class="call">
              <label class="toggle"
                ><input
                  type="checkbox"
                  v-model="config[name].enabled"
                  :disabled="busy"
                />
                {{
                  name === "rtc" ? "MatrixRTC (LiveKit + JWT)" : "coturn"
                }}</label
              >
              <div v-if="config[name].enabled">
                <cv-text-input
                  v-model="config[name].domain_name"
                  :label="$t('matrix.domain')"
                  :placeholder="name + '.example.com'"
                  :disabled="busy"
                />
                <cv-text-input
                  v-model="config[name].public_ip"
                  :label="$t('matrix.media_ip')"
                  :disabled="busy"
                />
              </div>
            </div>
            <p class="hint">{{ $t("matrix.call_hint") }}</p>
            <cv-text-input
              v-model="config.jitsi_domain_name"
              :label="$t('matrix.jitsi')"
              placeholder="meet.example.com"
              :disabled="busy"
            />
          </cv-tile>
          <cv-tile light class="section">
            <h3>{{ $t("matrix.extensions") }}</h3>
            <cv-text-input
              v-model="config.bridge_admin"
              :label="$t('matrix.bridge_admin')"
              :placeholder="'@administrator:' + config.server_name"
              :disabled="busy"
            />
            <p class="hint">{{ $t("matrix.extension_hint") }}</p>
            <div
              v-for="(part, name) in config.extensions"
              :key="name"
              class="extension"
            >
              <label class="toggle"
                ><input
                  type="checkbox"
                  v-model="part.enabled"
                  :disabled="busy"
                />
                <strong>{{ names[name] }}</strong></label
              >
              <div v-if="part.enabled">
                <cv-text-input
                  v-if="hostExtensions.includes(name)"
                  v-model="part.host"
                  :label="$t('matrix.domain')"
                  :placeholder="name + '.example.com'"
                  :disabled="busy"
                />
                <p
                  v-if="
                    [
                      'telegram',
                      'draupnir',
                      'buscarron',
                      'postmoogle',
                    ].includes(name)
                  "
                  class="hint"
                >
                  {{ $t("matrix.help_" + name) }}
                </p>
                <button
                  v-if="!loaded[name]"
                  type="button"
                  class="bx--btn bx--btn--tertiary"
                  @click="loadEditor(name)"
                  :disabled="busy"
                >
                  {{ $t("matrix.edit_config") }}
                </button>
                <div v-else>
                  <label :for="'config-' + name">{{
                    $t("matrix.config_json")
                  }}</label>
                  <textarea
                    :id="'config-' + name"
                    v-model="editors[name]"
                    rows="10"
                    class="config-editor"
                    :disabled="busy"
                    spellcheck="false"
                  />
                  <details>
                    <summary>{{ $t("matrix.defaults") }}</summary>
                    <pre>{{ upstream[name] }}</pre>
                  </details>
                </div>
              </div>
            </div>
          </cv-tile>
          <cv-tile light class="section">
            <h3>{{ $t("matrix.maintenance") }}</h3>
            <label class="toggle"
              ><input
                type="checkbox"
                v-model="config.auto_compressor"
                :disabled="busy"
              />
              {{ $t("matrix.compressor") }}</label
            >
            <p class="hint">{{ $t("matrix.backup_hint") }}</p>
            <button
              v-if="!loaded.synapse"
              type="button"
              class="bx--btn bx--btn--tertiary"
              @click="loadEditor('synapse')"
              :disabled="busy"
            >
              {{ $t("matrix.synapse_extra") }}
            </button>
            <textarea
              v-else
              v-model="editors.synapse"
              :aria-label="$t('matrix.synapse_extra')"
              rows="8"
              class="config-editor"
              :disabled="busy"
              spellcheck="false"
            />
          </cv-tile>
          <cv-tile v-if="config.configured" light class="section">
            <details @toggle="loadRecovery">
              <summary>{{ $t("matrix.recovery") }}</summary>
              <p class="hint">{{ $t("matrix.recovery_hint") }}</p>
              <div v-if="recovery">
                <p>{{ recovery.user }}</p>
                <code>{{ recovery.password }}</code>
                <p v-if="recovery.maubot_password">
                  maubot: {{ recovery.maubot_user }} —
                  <code>{{ recovery.maubot_password }}</code>
                </p>
                <p>
                  <button
                    type="button"
                    class="bx--btn bx--btn--tertiary"
                    @click="rotateRecovery"
                    :disabled="busy"
                  >
                    {{ $t("matrix.rotate_password") }}
                  </button>
                </p>
              </div>
            </details>
          </cv-tile>
          <button
            type="submit"
            class="bx--btn bx--btn--primary"
            :disabled="busy"
          >
            {{ busy ? $t("common.processing") : $t("settings.save") }}
          </button>
          <p v-if="saved" role="status" class="saved">
            {{ $t("matrix.saved") }}
          </p>
        </cv-form>
      </cv-column></cv-row
    >
  </cv-grid>
</template>
<script>
import { mapState } from "vuex";
import {
  TaskService,
  UtilService,
  QueryParamService,
} from "@nethserver/ns8-ui-lib";
import MatrixTasks from "../matrix-tasks";

export default {
  name: "Settings",
  mixins: [TaskService, UtilService, QueryParamService, MatrixTasks],
  data() {
    return {
      config: null,
      busy: false,
      error: "",
      saved: false,
      recovery: null,
      editors: {},
      loaded: {},
      upstream: {},
      hostExtensions: ["ketesa", "maubot", "hookshot", "buscarron"],
      names: {
        discord: "mautrix-discord",
        telegram: "mautrix-telegram",
        whatsapp: "mautrix-whatsapp",
        signal: "mautrix-signal",
        heisenbridge: "Heisenbridge (IRC)",
        hookshot: "Matrix Hookshot",
        steam: "Matrix Steam Bridge",
        postmoogle: "Postmoogle",
        maubot: "maubot",
        draupnir: "Draupnir",
        buscarron: "Buscarron",
        ketesa: "Ketesa",
      },
    };
  },
  computed: { ...mapState(["instanceName", "core", "appName"]) },
  created() {
    this.reload();
  },
  methods: {
    async reload() {
      this.busy = true;
      try {
        this.config = await this.matrixTask("get-configuration");
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
    async loadEditor(name) {
      this.busy = true;
      this.error = "";
      try {
        const result = await this.matrixTask("get-extension-config", { name });
        const examples = {
          telegram: { network: { api_id: 0, api_hash: "" } },
          draupnir: { managementRoom: "!room:" + this.config.server_name },
          buscarron: {
            BUSCARRON_LIST: "contact",
            BUSCARRON_CONTACT_ROOM: "!room:" + this.config.server_name,
          },
          postmoogle: { POSTMOOGLE_DOMAINS: this.config.server_name },
        };
        this.$set(
          this.editors,
          name,
          JSON.stringify(
            Object.keys(result.config).length
              ? result.config
              : examples[name] || {},
            null,
            2
          )
        );
        this.$set(
          this.upstream,
          name,
          JSON.stringify(result.defaults, null, 2)
        );
        this.$set(this.loaded, name, true);
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
    async save() {
      this.busy = true;
      this.error = "";
      this.saved = false;
      try {
        const data = JSON.parse(JSON.stringify(this.config));
        ["configured", "domains_list", "ports"].forEach(
          (key) => delete data[key]
        );
        for (const [name, part] of Object.entries(data.extensions)) {
          delete part.has_config;
          if (this.loaded[name]) part.config = JSON.parse(this.editors[name]);
        }
        if (this.loaded.synapse)
          data.synapse_extra = JSON.parse(this.editors.synapse);
        await this.matrixTask("configure-module", data, false);
        this.saved = true;
        this.config = await this.matrixTask("get-configuration");
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
    async loadRecovery(event) {
      if (!event.target.open || this.recovery) return;
      this.busy = true;
      try {
        this.recovery = await this.matrixTask("get-recovery-admin");
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
    async rotateRecovery() {
      this.busy = true;
      try {
        this.recovery = await this.matrixTask("rotate-recovery-admin");
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
  },
};
</script>
<style scoped lang="scss">
@import "../styles/carbon-utils";
.section {
  margin-bottom: 1.5rem;
}
h3 {
  margin-bottom: 1rem;
}
.hint {
  font-size: 0.875rem;
  color: #525252;
  margin: 0.5rem 0 1rem;
}
.toggle {
  display: block;
  margin: 1rem 0;
  cursor: pointer;
}
.toggle input {
  margin-right: 0.5rem;
}
.extension {
  border-top: 1px solid #e0e0e0;
  padding: 0.5rem 0 1rem;
}
.config-editor {
  width: 100%;
  padding: 0.75rem;
  font-family: monospace;
  border: 1px solid #8d8d8d;
  margin: 0.5rem 0;
}
summary {
  cursor: pointer;
  margin: 1rem 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 24rem;
  overflow: auto;
  padding: 1rem;
  background: #f4f4f4;
}
code {
  overflow-wrap: anywhere;
}
.saved {
  margin-top: 1rem;
  color: #198038;
}
</style>
