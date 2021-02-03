import { Directive, HostBinding, ViewContainerRef } from '@angular/core';

@Directive({
  selector: `[appViewSelector], .modal-body, .modal-title`
})
export class ViewSelectorDirective {
  @HostBinding('tabindex') tabIndex = '-1';
  constructor(public view: ViewContainerRef) { }

}
