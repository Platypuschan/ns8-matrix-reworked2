<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<template>
  <cv-grid fullWidth>
    <cv-row
      ><cv-column class="page-title"
        ><h2>{{ $t("status.title") }}</h2></cv-column
      ></cv-row
    >
    <cv-row
      ><cv-column>
        <NsInlineNotification
          v-if="error"
          kind="error"
          :title="$t('matrix.failed')"
          :description="error"
          :showCloseButton="false"
        />
        <cv-tile light v-if="status">
          <p v-if="!status.configured">
            {{ $t("matrix.configure_first") }}
            <router-link to="/settings">{{ $t("settings.title") }}</router-link>
          </p>
          <p v-if="status.restart_pending">{{ $t("matrix.pending") }}</p>
          <table v-if="status.services.length" class="services">
            <thead>
              <tr>
                <th>{{ $t("status.services") }}</th>
                <th>{{ $t("status.title") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="service in status.services" :key="service.name">
                <td>{{ service.name }}</td>
                <td :class="service.state === 'active' ? 'active' : 'inactive'">
                  {{ service.state }}
                </td>
              </tr>
            </tbody>
          </table>
          <ul class="links">
            <li v-for="link in status.links" :key="link.name">
              <a :href="link.url" target="_blank" rel="noopener noreferrer"
                >{{ link.name }} — {{ link.url }}</a
              >
            </li>
          </ul>
          <p v-if="status.ports.length">
            {{ $t("matrix.public_ports") }}: {{ status.ports.join(", ") }}
          </p>
          <p class="hint">{{ $t("matrix.port_hint") }}</p>
          <button
            type="button"
            class="bx--btn bx--btn--tertiary"
            @click="refresh"
            :disabled="busy"
          >
            {{ $t("matrix.refresh") }}
          </button>
        </cv-tile>
      </cv-column></cv-row
    >
  </cv-grid>
</template>
<script>
import { mapState } from "vuex";
import { TaskService, UtilService } from "@nethserver/ns8-ui-lib";
import MatrixTasks from "../matrix-tasks";
export default {
  name: "Status",
  mixins: [TaskService, UtilService, MatrixTasks],
  data() {
    return { status: null, error: "", busy: false };
  },
  computed: { ...mapState(["instanceName", "core"]) },
  created() {
    this.refresh();
  },
  methods: {
    async refresh() {
      this.busy = true;
      this.error = "";
      try {
        this.status = await this.matrixTask("get-stack-status");
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
.services {
  width: 100%;
  text-align: left;
  margin-bottom: 1.5rem;
}
th,
td {
  padding: 0.75rem;
  border-bottom: 1px solid #e0e0e0;
}
.active {
  color: #198038;
}
.inactive {
  color: #da1e28;
}
.links {
  list-style: none;
  line-height: 2;
}
.hint {
  margin: 1rem 0;
  font-size: 0.875rem;
  color: #525252;
}
</style>
