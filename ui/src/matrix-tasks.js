// SPDX-License-Identifier: AGPL-3.0-or-later
export default {
  methods: {
    matrixTask(action, data = {}, hidden = true) {
      const eventId = this.getUuid();
      return new Promise((resolve, reject) => {
        const completed = `${action}-completed-${eventId}`;
        const aborted = `${action}-aborted-${eventId}`;
        const invalid = `${action}-validation-failed-${eventId}`;
        const cleanup = () => {
          [completed, aborted, invalid].forEach((event) =>
            this.core.$root.$off(event)
          );
        };
        this.core.$root.$once(completed, (context, result) => {
          cleanup();
          resolve(result.output);
        });
        this.core.$root.$once(aborted, () => {
          cleanup();
          reject(new Error(this.$t("matrix.failed")));
        });
        this.core.$root.$once(invalid, (errors) => {
          cleanup();
          reject(
            new Error(
              errors.map((item) => `${item.field}: ${item.error}`).join("; ")
            )
          );
        });
        this.createModuleTaskForApp(this.instanceName, {
          action,
          data,
          extra: {
            title: this.$t("action." + action),
            isNotificationHidden: hidden,
            eventId,
          },
        }).catch((error) => {
          cleanup();
          reject(error);
        });
      });
    },
  },
};
